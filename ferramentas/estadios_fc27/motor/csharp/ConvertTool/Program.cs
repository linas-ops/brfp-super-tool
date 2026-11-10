// FIFA 16 -> FC27 conversion jobs on the FIFA Editor Tool SDK object model (FC27, editor 17.1.5.0).
// ConvertTool <FC27SDK.dll> <gameDir> <jobs.json> <report.json>
// Kept apart from StadiumTool so the tool that reproduces the confirmed duplicates stays unchanged.
// Inputs are never modified; outputs are never overwritten; every written resource is re-read.
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Sdk;
using Sdk.Ebx;
using Sdk.Ebx.Serialization;
using Sdk.Games;
using Sdk.Reflection;
using Sdk.Resources;

static partial class Program
{
    static FileSystem fs;
    static FC27GameInfo game;
    static readonly JsonSerializerOptions Pretty = new() { WriteIndented = true, NumberHandling = System.Text.Json.Serialization.JsonNumberHandling.AllowNamedFloatingPointLiterals, TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver() };

    static int Main(string[] args)
    {
        if (args.Length != 4) { Console.Error.WriteLine("usage: ConvertTool FC27SDK.dll gameDir jobs.json report.json"); return 2; }
        if (File.Exists(args[3])) { Console.Error.WriteLine("report exists: " + args[3]); return 2; }
        game = new FC27GameInfo();
        TypeRegistry.Initialize(Path.GetFullPath(args[0]));
        TypeRegistry.WarmUpMappings();
        fs = new FileSystem(args[1]);
        fs.Initialize(Keys.InitFsKey, checkTocs: false);
        typeof(BaseEbxPartitionReader).Assembly.GetType("Sdk.Ebx.Serialization.Riff.EbxSharedTypeDescriptorTable")!
            .GetMethod("Initialize")!.Invoke(null, new object[] { fs });
        var batch = JsonNode.Parse(File.ReadAllText(args[2]))!.AsObject();
        var rows = new JsonArray();
        int failed = 0;
        foreach (var node in batch["jobs"]!.AsArray())
        {
            var job = node!.AsObject();
            var row = new JsonObject { ["kind"] = (string)job["kind"], ["input"] = (string)job["input"] };
            try
            {
                switch ((string)job["kind"])
                {
                    case "mesh_dump": MeshDump(job, row); break;
                    case "mesh_build": MeshBuild(job, row); break;
                    case "mesh_edit": MeshEdit(job, row); break;
                    case "texture_build": TextureBuild(job, row); break;
                    case "sbd_extend": SbdExtend(job, row); break;
                    case "ebx_ops": EbxOps(job, row); break;
                    case "ebx_dump": EbxDump(job, row); break;
                    case "mesh_fields": MeshFields(job, row); break;
                    case "ebx_imports":
                        {
                            var pp = ReadEbx(File.ReadAllBytes((string)job["input"]));
                            var io = Get(pp, "_importOrder") as System.Collections.IEnumerable;
                            var list = new JsonArray();
                            if (io != null)
                                foreach (var x in io)
                                {
                                    if (x is EbxImportReference ir) list.Add((JsonNode)(ir.PartitionGuid + "/" + ir.InstanceGuid));
                                    else list.Add((JsonNode)x?.ToString());
                                }
                            row["imports"] = list;
                            break;
                        }
                    case "ebx_order":
                        {
                            var pp = ReadEbx(File.ReadAllBytes((string)job["input"]));
                            try { CheckExportedOrder(pp); row["order_ok"] = true; }
                            catch (InvalidDataException ex) { row["order_ok"] = false; row["order_error"] = ex.Message; }
                            row["instances"] = pp.Instances.Count(); row["exported"] = pp.Instances.Count(i => i.InstanceId.IsExported);
                            break;
                        }
                    case "sbd_keys":
                        {
                            var depot = LoadSbd(File.ReadAllBytes((string)job["input"]), Convert.FromHexString((string)job["meta"]));
                            row["keys"] = new JsonArray(depot.Entries.Select(e => (JsonNode)e.KeyHash.ToString()).ToArray());
                            break;
                        }
                    case "clr_members":
                        {
                            var t = typeof(BaseEbxPartitionReader).Assembly.GetTypes().First(x => x.Name == (string)job["type"]);
                            row["type"] = t.FullName;
                            row["members"] = new JsonArray(t.GetMembers(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static)
                                .Select(m => (JsonNode)(m.MemberType + " " + m switch
                                {
                                    FieldInfo f => f.FieldType.Name + " " + f.Name,
                                    PropertyInfo pr => pr.PropertyType.Name + " " + pr.Name,
                                    MethodInfo mi => mi.ReturnType.Name + " " + mi.Name + "(" + string.Join(",", mi.GetParameters().Select(pa => pa.ParameterType.Name)) + ")",
                                    _ => m.Name
                                })).ToArray());
                            break;
                        }
                    case "type_layout":
                        {
                            var ti = TypeRegistry.GetType((string)job["type"]);
                            var t = ti.ClrType;
                            var fl = new JsonArray();
                            for (var tt = t; tt != null && tt != typeof(object); tt = tt.BaseType)
                                foreach (var m in tt.GetMembers(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly))
                                {
                                    var attrs = m.GetCustomAttributesData();
                                    if (attrs.Count == 0) continue;
                                    fl.Add(new JsonObject
                                    {
                                        ["owner"] = tt.Name, ["name"] = m.Name, ["kind"] = m.MemberType.ToString(),
                                        ["attrs"] = new JsonArray(attrs.Select(a => (JsonNode)(a.AttributeType.Name + "(" + string.Join(",", a.ConstructorArguments.Select(c => c.Value?.ToString()))
                                            + (a.NamedArguments.Count > 0 ? ";" + string.Join(",", a.NamedArguments.Select(na => na.MemberName + "=" + na.TypedValue.Value)) : "") + ")")).ToArray()),
                                    });
                                }
                            row["type"] = t.FullName; row["members"] = fl;
                            row["type_attrs"] = new JsonArray(t.GetCustomAttributesData().Select(a => (JsonNode)(a.AttributeType.Name + "(" + string.Join(",", a.ConstructorArguments.Select(c => c.Value?.ToString())) + ")")).ToArray());
                            break;
                        }
                    case "enum_names":
                        row["names"] = new JsonArray(Enum.GetNames(TypeRegistry.GetType((string)job["type"]).ClrType).Select(x => (JsonNode)x).ToArray());
                        break;
                    default: throw new InvalidDataException("unknown job kind");
                }
                row["ok"] = true;
            }
            catch (Exception ex)
            {
                while (ex is TargetInvocationException && ex.InnerException != null) ex = ex.InnerException;
                failed++; row["ok"] = false; row["error"] = ex.ToString();
            }
            rows.Add(row);
        }
        var report = new JsonObject { ["total"] = rows.Count, ["failed"] = failed, ["rows"] = rows };
        File.WriteAllText(args[3], report.ToJsonString(Pretty));
        Console.WriteLine(JsonSerializer.Serialize(new { total = rows.Count, failed }));
        return failed == 0 ? 0 : 1;
    }

    // ---------------------------------------------------------------- helpers
    static string Hex(byte[] b) => b == null ? null : Convert.ToHexString(b).ToLowerInvariant();
    static string Sha(byte[] b) => Convert.ToHexString(SHA256.HashData(b)).ToLowerInvariant();

    static object Get(object o, string field)
    {
        for (var t = o.GetType(); t != null; t = t.BaseType)
        {
            var f = t.GetField(field, BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance);
            if (f != null) return f.GetValue(o);
        }
        throw new MissingFieldException(o.GetType().Name, field);
    }

    static void Set(object o, string field, object value)
    {
        for (var t = o.GetType(); t != null; t = t.BaseType)
        {
            var f = t.GetField(field, BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance);
            if (f != null) { f.SetValue(o, value); return; }
        }
        throw new MissingFieldException(o.GetType().Name, field);
    }

    static MeshSet LoadMesh(byte[] data, byte[] meta) => new MeshSet(game, new MemoryStream(data), meta, true);

    static JsonArray Box(AxisAlignedBox b) => new JsonArray(b.Min.X, b.Min.Y, b.Min.Z, b.Max.X, b.Max.Y, b.Max.Z);

    static JsonObject Decl(GeometryDeclarationDesc d)
    {
        var els = new JsonArray();
        for (int i = 0; i < d.ElementCount; i++)
        {
            var e = d.Elements[i];
            els.Add(new JsonObject { ["usage"] = e.Usage.ToString(), ["format"] = e.Format.ToString(), ["offset"] = e.Offset, ["stream"] = e.StreamIndex });
        }
        var st = new JsonArray();
        for (int i = 0; i < d.StreamCount; i++) st.Add(new JsonObject { ["stride"] = d.Streams[i].Stride, ["class"] = d.Streams[i].Classification.ToString() });
        return new JsonObject { ["elements"] = els, ["streams"] = st };
    }

    // ---------------------------------------------------------------- mesh_fields
    // Every instance field of the MeshSet, its LODs and the first subsets, by reflection (scalars, short arrays as text).
    static void MeshFields(JsonObject job, JsonObject row)
    {
        var m = LoadMesh(File.ReadAllBytes((string)job["input"]), Convert.FromHexString((string)job["meta"]));
        static JsonObject Fields(object o)
        {
            var r = new JsonObject();
            for (var t = o.GetType(); t != null && t != typeof(object); t = t.BaseType)
                foreach (var f in t.GetFields(BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly))
                {
                    var v = f.GetValue(o);
                    string s = v switch
                    {
                        null => "null",
                        byte[] b => b.Length <= 64 ? Hex(b) : $"byte[{b.Length}]",
                        Array a => a.Length <= 16 ? "[" + string.Join(",", a.Cast<object>().Select(x => x?.ToString())) + "]" : $"{a.GetType().Name}[{a.Length}]",
                        System.Collections.ICollection c => $"{v.GetType().Name}(count={c.Count})",
                        _ => v.ToString()
                    };
                    r[t.Name + "." + f.Name] = s.Length > 300 ? s[..300] : s;
                }
            return r;
        }
        row["mesh"] = Fields(m);
        var lods = new JsonArray();
        foreach (var lod in m.Lods)
        {
            var lo = Fields(lod);
            var subs = new JsonArray();
            foreach (int si in new[] { 0, 1, lod.Subsets.Count - 1 }.Where(i => i >= 0 && i < lod.Subsets.Count).Distinct())
                subs.Add(Fields(lod.Subsets[si]));
            lo["subsets_sample"] = subs;
            lods.Add(lo);
        }
        row["lods"] = lods;
    }

    // ---------------------------------------------------------------- mesh_dump
    static void MeshDump(JsonObject job, JsonObject row)
    {
        var data = File.ReadAllBytes((string)job["input"]);
        var meta = Convert.FromHexString((string)job["meta"]);
        var m = LoadMesh(data, (byte[])meta.Clone());
        row["roundtrip_identical"] = m.ToStream(game).ToArray().AsSpan().SequenceEqual(data);
        var o = new JsonObject
        {
            ["name"] = m.Name, ["type"] = m.Type.ToString(), ["flags"] = m.Flags.ToString(), ["tangent"] = m.TangentSpaceCompression.ToString(),
            ["bbox"] = Box(m.BoundingBox), ["name_hash"] = Get(m, "_nameHash").ToString(), ["vertex_index_size"] = m.VertexIndexSize,
            ["lod_fade"] = new JsonArray(((ushort[])Get(m, "_lodFadeDistanceFactors")).Select(x => (JsonNode)x).ToArray()),
            ["subset_start"] = new JsonArray(((ushort[])Get(m, "_subsetStartIndices")).Select(x => (JsonNode)x).ToArray()),
            ["subset_sort"] = Hex((byte[])Get(m, "_subsetSortIndices")), ["sort_count"] = (ushort)Get(m, "_subsetSortIndexCount"),
            ["draw_order"] = new JsonArray((ushort)Get(m, "_shaderDrawOrder"), (ushort)Get(m, "_shaderDrawOrderUserSlot"), (short)Get(m, "_shaderDrawOrderSubOrder")),
            ["after_tangent"] = Hex((byte[])Get(m, "_unknownAfterTangentSpaceCompression")), ["part_count"] = m.PartCount,
            ["meta"] = Hex(m.Meta),
        };
        static JsonArray V(Vec3 v) => new JsonArray(v.X, v.Y, v.Z);
        if (m.PartTransforms != null)
            o["parts"] = new JsonArray(m.PartTransforms.Select(t => (JsonNode)new JsonObject { ["right"] = V(t.Right), ["up"] = V(t.Up), ["forward"] = V(t.Forward), ["trans"] = V(t.Trans) }).ToArray());
        var pb = (AxisAlignedBox[])Get(m, "_partBoundingBoxes");
        if (pb != null) o["part_boxes"] = new JsonArray(pb.Select(b => (JsonNode)Box(b)).ToArray());
        var lods = new JsonArray();
        foreach (var lod in m.Lods)
        {
            var subs = new JsonArray();
            for (int si = 0; si < lod.Subsets.Count; si++)
            {
                var s = lod.Subsets[si];
                subs.Add(new JsonObject
                {
                    ["material"] = s.MaterialName, ["material_index"] = s.MaterialIndex, ["prims"] = s.PrimitiveCount, ["start"] = s.StartIndex,
                    ["vertex_offset"] = s.VertexOffset, ["vertices"] = s.VertexCount, ["stride"] = (byte)Get(s, "_vertexStride"),
                    ["prim_type"] = s.PrimitiveType.ToString(), ["flags"] = s.Flags.ToString(), ["key"] = s.ShaderExpressionInstanceKey.ToString(),
                    ["material_hash"] = s.MaterialNameHash, ["surface_area"] = s.SurfaceArea, ["lightmap_uv"] = s.LightMapUvMappingIndex,
                    ["bbox"] = Box((AxisAlignedBox)Get(s, "_boundingBox")), ["bones_per_vertex"] = s.BonesPerVertex,
                    ["tex_per_meter"] = new JsonArray(((float[])Get(s, "_texCoordsPerMeter")).Select(x => (JsonNode)x).ToArray()),
                    ["after_vertex"] = Hex((byte[])Get(s, "_unknownAfterVertexData")), ["trailer"] = Hex((byte[])Get(s, "_unknownTrailerData")),
                    ["scale"] = Hex((byte[])Get(s, "_unknownScale")), ["unknown2"] = (uint)Get(s, "_unknown2"),
                    ["before_area"] = (byte)Get(s, "_unknownBeforeSurfaceArea"), ["bones_flags"] = (ushort)Get(s, "_bonesPerVertexAndFlags"),
                    ["start_copy"] = (uint)Get(s, "_startIndexCopy"), ["decl_ptr"] = ((long)Get(s, "_geometryDeclarationsPointer")).ToString(),
                    ["decl0"] = Decl(s.GeometryDeclarationDescriptors[0]),
                    ["decl1"] = s.GeometryDeclarationDescriptors.Length > 1 ? Decl(s.GeometryDeclarationDescriptors[1]) : null,
                    ["parts"] = lod.SubsetPartIndices != null ? Hex(lod.SubsetPartIndices[si]) : null,
                });
            }
            lods.Add(new JsonObject
            {
                ["name"] = lod.Name, ["short"] = lod.ShortName, ["type"] = lod.Type.ToString(), ["flags"] = lod.Flags.ToString(),
                ["index_unit"] = lod.IndexUnitSize, ["index_size"] = lod.IndexDataSize, ["vertex_size"] = lod.VertexDataSize,
                ["chunk"] = lod.DataChunkId.ToString(), ["inline"] = lod.InlineDataLength, ["gpu_layout"] = Hex(lod.AdditionalGpuBufferLayout.ToArray()),
                ["alt_offset"] = lod.AlternateDataOffset, ["name_hash"] = lod.NameHash, ["max_stream_instances"] = (uint)Get(lod, "_maxStreamInstanceCount"),
                ["shader_debug_name"] = (string)Get(lod, "_shaderDebugName"),
                ["categories"] = new JsonArray(lod.CategorySubsetIndices.Select(c => (JsonNode)new JsonArray(c.Select(x => (JsonNode)x).ToArray())).ToArray()),
                ["subsets"] = subs,
            });
        }
        o["lods"] = lods;
        var output = (string)job["output"];
        if (File.Exists(output)) throw new IOException("output exists: " + output);
        File.WriteAllText(output, o.ToJsonString(Pretty));
        row["output"] = output;
    }
}
