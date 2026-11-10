// Offline EBX tool on the FIFA Editor Tool SDK object model (FC27, editor 17.1.5.0).
// StadiumTool <FC27SDK.dll> <gameDir> <jobs.json> <report.json>
// Jobs: dump | roundtrip | clone | slm_add | loader_register. Inputs are never modified; every
// written partition is re-read, validated and written a second time (the two writes must match).
using System.Collections;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Sdk;
using Sdk.Ebx;
using Sdk.Ebx.Serialization;
using Sdk.Games;
using Sdk.Reflection;

static class Program
{
    static FileSystem fs;
    static FC27GameInfo game;
    static readonly JsonSerializerOptions Pretty = new() { WriteIndented = true, TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver() };

    static int Main(string[] args)
    {
        if (args.Length != 4) { Console.Error.WriteLine("usage: StadiumTool FC27SDK.dll gameDir jobs.json report.json"); return 2; }
        if (File.Exists(args[3])) { Console.Error.WriteLine("report exists: " + args[3]); return 2; }
        game = new FC27GameInfo();
        TypeRegistry.Initialize(Path.GetFullPath(args[0]));
        TypeRegistry.WarmUpMappings();
        fs = new FileSystem(args[1]);
        fs.Initialize(Keys.InitFsKey, checkTocs: false);
        typeof(BaseEbxPartitionReader).Assembly.GetType("Sdk.Ebx.Serialization.Riff.EbxSharedTypeDescriptorTable")!
            .GetMethod("Initialize")!.Invoke(null, new object[] { fs });
        var batch = JsonNode.Parse(File.ReadAllText(args[2]))!.AsObject();
        var global = new Mapping(batch);
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
                    case "dump": Dump(job, row); break;
                    case "roundtrip": RoundTrip(job, row); break;
                    case "clone": Clone(job, global, row); break;
                    case "slm_add": SlmAdd(job, row); break;
                    case "loader_register": LoaderRegister(job, row); break;
                    case "hashes": Hashes(job, row); break;
                    case "fsinfo": FsInfo(job, row); break;
                    case "mesh_info": MeshInfo(job, row); break;
                    case "mesh_res": MeshRes(job, row); break;
                    case "texture_info": TextureInfo(job, row); break;
                    case "texture_res": TextureRes(job, row); break;
                    case "sbd_info": SbdInfo(job, row); break;
                    case "sbd_alias": SbdAlias(job, row); break;
                    case "alias_keys": AliasKeys(job, row); break;
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

    // ---------------------------------------------------------------- serialization
    static EbxPartition Read(byte[] bytes)
    {
        using var source = new MemoryStream(bytes);
        using var reader = BaseEbxPartitionReader.CreateReader(source, fs, game.FrostbiteVersion);
        return reader.ReadPartition<EbxPartition>();
    }

    static byte[] Write(EbxPartition p)
    {
        using var destination = new MemoryStream();
        using (var writer = BaseEbxPartitionWriter.CreateWriter(destination, fs, game.FrostbiteVersion, leaveOpen: true)) writer.WritePartition(p);
        return destination.ToArray();
    }

    static string Sha(byte[] b) => Convert.ToHexString(SHA256.HashData(b)).ToLowerInvariant();

    static void Save(JsonObject job, JsonObject row, EbxPartition p, string expectName, string expectType, Guid expectPartition)
    {
        var first = Write(p);
        var again = Read(first);
        var snapBefore = Snapshot.Of(p);
        var snapAfter = Snapshot.Of(again);
        if (snapBefore.Key != snapAfter.Key) throw new InvalidDataException("partition graph changed by serialization:\n" + snapBefore.Key + "\n" + snapAfter.Key);
        var second = Write(again);
        if (!first.AsSpan().SequenceEqual(second)) throw new InvalidDataException("second write differs from first write");
        CheckRoot(again, expectName, expectType, expectPartition);
        var output = (string)job["output"];
        if (File.Exists(output)) throw new IOException("output exists: " + output);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        File.WriteAllBytes(output, first);
        row["output"] = output; row["sha256"] = Sha(first); row["bytes"] = first.Length;
        row["root_name"] = expectName; row["root_type"] = expectType; row["partition"] = expectPartition.ToString();
        row["instances"] = snapAfter.Instances; row["exports"] = snapAfter.Exports;
        row["internal_pointers"] = snapAfter.Internal; row["external_pointers"] = snapAfter.External;
        row["second_write_stable"] = true;
        row["imports"] = new JsonArray(snapAfter.Imports.Select(x => (JsonNode)x).ToArray());
    }

    static void CheckRoot(EbxPartition p, string name, string type, Guid partition)
    {
        var primary = p.PrimaryInstance;
        var actual = primary.GetType().GetProperty("Name")?.GetValue(primary) as string;
        if (!string.Equals(actual, name, StringComparison.Ordinal)) throw new InvalidDataException($"root name '{actual}' != '{name}'");
        if (primary.GetType().Name != type) throw new InvalidDataException($"root type {primary.GetType().Name} != {type}");
        if (p.PartitionGuid != partition) throw new InvalidDataException($"partition {p.PartitionGuid} != {partition}");
    }

    static string RootName(EbxPartition p) => p.PrimaryInstance.GetType().GetProperty("Name")?.GetValue(p.PrimaryInstance) as string;

    // ---------------------------------------------------------------- reflection helpers
    static readonly Dictionary<Type, PropertyInfo[]> propsCache = new();

    static PropertyInfo[] Fields(Type t)
    {
        if (propsCache.TryGetValue(t, out var cached)) return cached;
        var list = new List<PropertyInfo>();
        for (var x = t; x != null && x != typeof(object) && x != typeof(ValueType); x = x.BaseType)
            foreach (var p in x.GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly))
                if (p.CanRead && p.CanWrite && p.GetIndexParameters().Length == 0 && p.GetCustomAttributes().Any(a => a.GetType().Name == "NameHashAttribute"))
                    list.Add(p);
        return propsCache[t] = list.ToArray();
    }

    static bool IsLeaf(object v) => v is string || v is Guid || v is decimal || v is ResourceRef || v is FileRef || v is TypeRef
        || v is EbxInstanceId || v.GetType().IsPrimitive || v.GetType().IsEnum;

    static bool IsFrostbite(Type t) => t.Namespace?.StartsWith("Frostbite", StringComparison.Ordinal) == true;

    // ---------------------------------------------------------------- dump
    static void Dump(JsonObject job, JsonObject row)
    {
        var p = Read(File.ReadAllBytes((string)job["input"]));
        var index = new Dictionary<object, int>(ReferenceEqualityComparer.Instance);
        int i = 0;
        foreach (var inst in p.Instances) index[inst] = i++;
        var instances = new JsonArray();
        foreach (var inst in p.Instances)
        {
            var id = inst.InstanceId;
            instances.Add(new JsonObject
            {
                ["index"] = index[inst], ["guid"] = id.InstanceGuid.ToString(), ["exported"] = id.IsExported,
                ["type"] = inst.GetType().FullName, ["fields"] = DumpValue(inst, index, 0)
            });
        }
        var doc = new JsonObject
        {
            ["partition"] = p.PartitionGuid.ToString(), ["name"] = RootName(p), ["type"] = p.PrimaryInstance.GetType().Name,
            ["instances"] = instances
        };
        var output = (string)job["output"];
        if (File.Exists(output)) throw new IOException("output exists: " + output);
        File.WriteAllText(output, doc.ToJsonString(Pretty));
        row["output"] = output; row["name"] = RootName(p); row["type"] = p.PrimaryInstance.GetType().Name;
        row["partition"] = p.PartitionGuid.ToString(); row["instance_count"] = i;
    }

    static JsonNode DumpValue(object v, Dictionary<object, int> index, int depth)
    {
        if (v == null) return null;
        if (depth > 40) return "<depth>";
        switch (v)
        {
            case string s: return s;
            case bool b: return b;
            case Guid g: return "guid:" + g;
            case PointerRef pr:
                return pr.Type switch
                {
                    PointerRefType.Null => "ptr:null",
                    PointerRefType.Internal => "ptr:int:" + (pr.Internal != null && index.TryGetValue(pr.Internal, out var k) ? k : -1),
                    _ => "ptr:ext:" + pr.External.PartitionGuid + "/" + pr.External.InstanceGuid
                };
            case ResourceRef rr: return "res:" + rr;
            case FileRef fr: return "file:" + (string)fr;
            case TypeRef tr: return "type:" + tr.Name + "/" + tr.Guid;
            case BoxedValueRef bx: return new JsonObject { ["boxed"] = bx.Value == null ? null : DumpValue(bx.Value, index, depth + 1) };
        }
        var t = v.GetType();
        if (t.IsEnum) return v.ToString();
        if (t.IsPrimitive || v is decimal) return JsonValue.Create(Convert.ToDouble(v));
        if (v is IList list)
        {
            var a = new JsonArray();
            foreach (var x in list) a.Add(DumpValue(x, index, depth + 1));
            return a;
        }
        var o = new JsonObject();
        if (depth > 0 && v is IEbxInstance) return "inst:" + (index.TryGetValue(v, out var n) ? n : -1);
        foreach (var p in Fields(t)) o[p.Name] = DumpValue(p.GetValue(v), index, depth + 1);
        if (depth > 0) o["$type"] = t.Name;
        return o;
    }

    // ---------------------------------------------------------------- round trip
    static void RoundTrip(JsonObject job, JsonObject row)
    {
        var input = File.ReadAllBytes((string)job["input"]);
        var p = Read(input);
        row["input_sha256"] = Sha(input);
        Save(job, row, p, RootName(p), p.PrimaryInstance.GetType().Name, p.PartitionGuid);
        row["input_byte_identical"] = Sha(input) == (string)row["sha256"];
    }

    // ---------------------------------------------------------------- clone
    sealed class Mapping
    {
        public readonly Dictionary<(Guid, Guid), (Guid, Guid)> Pairs = new();
        // Exact (ordinal) string occurrences: the planner lists every spelling it found.
        public readonly Dictionary<string, string> Strings = new(StringComparer.Ordinal);
        public readonly Dictionary<Guid, Guid> Guids = new();
        public readonly HashSet<Guid> ClonedPartitions = new();
        public readonly List<string> Watch = new();
        // ResourceRef (RID) remapping for cloned RES, and name-hash fields remapped by exact field name.
        public readonly Dictionary<ulong, ulong> Resources = new();
        public readonly Dictionary<string, Dictionary<ulong, ulong>> UintFields = new(StringComparer.Ordinal);

        public Mapping(JsonObject batch)
        {
            if (batch["pairs"] is JsonArray pairs)
                foreach (var e in pairs)
                {
                    var a = e!.AsArray();
                    var key = (Guid.Parse((string)a[0]), Guid.Parse((string)a[1]));
                    if (!Pairs.TryAdd(key, (Guid.Parse((string)a[2]), Guid.Parse((string)a[3])))) throw new InvalidDataException("duplicate pair " + key);
                    ClonedPartitions.Add(key.Item1);
                }
            if (batch["strings"] is JsonObject strings)
                foreach (var kv in strings) if (!Strings.TryAdd(kv.Key, (string)kv.Value)) throw new InvalidDataException("duplicate string " + kv.Key);
            if (batch["guids"] is JsonObject guids)
                foreach (var kv in guids) Guids.Add(Guid.Parse(kv.Key), Guid.Parse((string)kv.Value));
            if (batch["watch"] is JsonArray watch) foreach (var w in watch) Watch.Add((string)w);
            if (batch["resources"] is JsonObject res)
                foreach (var kv in res) Resources.Add(ulong.Parse(kv.Key), ulong.Parse((string)kv.Value));
            if (batch["uint_fields"] is JsonObject uf)
                foreach (var kv in uf)
                {
                    var map = new Dictionary<ulong, ulong>();
                    foreach (var e in kv.Value!.AsObject()) map.Add(ulong.Parse(e.Key), ulong.Parse((string)e.Value));
                    UintFields.Add(kv.Key, map);
                }
        }
    }

    sealed class Rewriter
    {
        readonly Mapping m;
        readonly HashSet<object> visited = new(ReferenceEqualityComparer.Instance);
        public readonly JsonArray Changes = new();
        public readonly JsonArray Watched = new();
        public readonly JsonArray GuidValues = new();
        public Rewriter(Mapping mapping) { m = mapping; }

        public void Run(EbxPartition p)
        {
            int i = 0;
            foreach (var inst in p.Instances) { Walk(inst, "[" + i + "]" + inst.GetType().Name); i++; }
        }

        object Walk(object v, string path)
        {
            if (v == null) return null;
            switch (v)
            {
                case string s:
                    if (m.Strings.TryGetValue(s, out var ns)) { Changes.Add($"{path}: '{s}' -> '{ns}'"); return ns; }
                    foreach (var w in m.Watch) if (s.Contains(w, StringComparison.OrdinalIgnoreCase)) { Watched.Add($"{path}: '{s}'"); break; }
                    return s;
                case FileRef fr:
                    var fs_ = (string)fr;
                    if (m.Strings.TryGetValue(fs_, out var nf)) { Changes.Add($"{path}: file '{fs_}' -> '{nf}'"); return new FileRef(nf); }
                    foreach (var w in m.Watch) if (fs_.Contains(w, StringComparison.OrdinalIgnoreCase)) { Watched.Add($"{path}: file '{fs_}'"); break; }
                    return fr;
                case PointerRef pr:
                    if (pr.Type == PointerRefType.External)
                    {
                        var key = (pr.External.PartitionGuid, pr.External.InstanceGuid);
                        if (m.Pairs.TryGetValue(key, out var to))
                        {
                            Changes.Add($"{path}: ext {key.Item1}/{key.Item2} -> {to.Item1}/{to.Item2}");
                            return new PointerRef(new EbxImportReference { PartitionGuid = to.Item1, InstanceGuid = to.Item2 });
                        }
                        if (m.ClonedPartitions.Contains(key.Item1)) throw new InvalidDataException($"{path}: external ref into cloned partition without pair mapping {key.Item1}/{key.Item2}");
                    }
                    return pr;
                case Guid g:
                    if (g != Guid.Empty)
                    {
                        if (m.Guids.TryGetValue(g, out var ng)) { Changes.Add($"{path}: guid {g} -> {ng}"); return ng; }
                        GuidValues.Add($"{path}: {g}");
                    }
                    return g;
                case BoxedValueRef bx:
                    if (bx.Value != null)
                    {
                        var nv = Walk(bx.Value, path + ".<boxed>");
                        if (!ReferenceEquals(nv, bx.Value) || nv.GetType().IsValueType) bx.SetValue(nv);
                    }
                    return bx;
                case ResourceRef rr:
                    ulong rid = rr;
                    if (rid != 0 && m.Resources.TryGetValue(rid, out var nrid)) { Changes.Add($"{path}: rid {rid:X16} -> {nrid:X16}"); return new ResourceRef(nrid); }
                    if (rid != 0) ResourceValues.Add($"{path}: {rid:X16}");
                    return rr;
            }
            if (IsLeaf(v)) return v;
            var t = v.GetType();
            if (!t.IsValueType && !visited.Add(v)) return v;
            if (v is IList list)
            {
                for (int i = 0; i < list.Count; i++)
                {
                    var item = list[i];
                    var ni = Walk(item, path + "[" + i + "]");
                    if (!ReferenceEquals(ni, item) || (ni != null && ni.GetType().IsValueType)) list[i] = ni;
                }
                return v;
            }
            if (!IsFrostbite(t)) return v;
            foreach (var p in Fields(t))
            {
                var cur = p.GetValue(v);
                if (cur == null) continue;
                if ((cur is uint || cur is ulong) && m.UintFields.TryGetValue(p.Name, out var hm))
                {
                    ulong old = cur is uint u32 ? u32 : (ulong)cur;
                    if (hm.TryGetValue(old, out var nh))
                    {
                        Changes.Add($"{path}.{p.Name}: {old} -> {nh}");
                        p.SetValue(v, cur is uint ? (object)checked((uint)nh) : nh);
                    }
                    continue;
                }
                var nv = Walk(cur, path + "." + p.Name);
                if (!ReferenceEquals(nv, cur) || nv.GetType().IsValueType) p.SetValue(v, nv);
            }
            return v;
        }
        public readonly JsonArray ResourceValues = new();
    }

    static void Clone(JsonObject job, Mapping global, JsonObject row)
    {
        var input = File.ReadAllBytes((string)job["input"]);
        var p = Read(input);
        var oldName = RootName(p);
        if ((string)job["expect_name"] != oldName) throw new InvalidDataException($"input root name '{oldName}' != expected '{job["expect_name"]}'");
        var type = p.PrimaryInstance.GetType().Name;
        if ((string)job["expect_type"] != type) throw new InvalidDataException($"input type {type} != {job["expect_type"]}");
        var oldPartition = p.PartitionGuid;
        if (Guid.Parse((string)job["expect_partition"]) != oldPartition) throw new InvalidDataException("input partition mismatch");
        var newPartition = Guid.Parse((string)job["partition"]);
        var before = Snapshot.Of(p);
        // Exported instance identities: every exported instance needs a pair mapping.
        var exported = new JsonArray();
        foreach (var inst in p.Instances)
        {
            var id = inst.InstanceId;
            if (!id.IsExported) continue;
            if (!global.Pairs.TryGetValue((oldPartition, id.InstanceGuid), out var to) || to.Item1 != newPartition)
                throw new InvalidDataException($"no pair mapping for exported instance {oldPartition}/{id.InstanceGuid}");
            inst.InstanceId = new EbxInstanceId(to.Item2, id.Index, true);
            exported.Add($"{id.InstanceGuid} -> {to.Item2}");
        }
        p.SetPartitionGuid(newPartition);
        var rw = new Rewriter(global);
        rw.Run(p);
        // Explicit primary-instance fields (e.g. mesh NameHash = Djb2 32 of the new name, as FET sets it).
        if (job["set_primary"] is JsonObject sets)
            foreach (var kv in sets)
            {
                var prop = p.PrimaryInstance.GetType().GetProperty(kv.Key) ?? throw new InvalidDataException("no field " + kv.Key);
                var before0 = prop.GetValue(p.PrimaryInstance);
                object value = prop.PropertyType == typeof(uint) ? (object)uint.Parse((string)kv.Value) : prop.PropertyType == typeof(ulong) ? ulong.Parse((string)kv.Value) : throw new InvalidDataException("unsupported field type " + kv.Key);
                prop.SetValue(p.PrimaryInstance, value);
                rw.Changes.Add($"primary.{kv.Key}: {before0} -> {value}");
            }
        var newName = RootName(p);
        if ((string)job["new_name"] != newName) throw new InvalidDataException($"root name after rewrite '{newName}' != '{job["new_name"]}'");
        var after = Snapshot.Of(p);
        if (before.Instances != after.Instances || before.Exports != after.Exports || before.Internal != after.Internal || before.External != after.External)
            throw new InvalidDataException("instance/pointer counts changed during rewrite");
        foreach (var imp in after.Imports)
        {
            var parts = imp.Split('/');
            if (global.Pairs.ContainsKey((Guid.Parse(parts[0]), Guid.Parse(parts[1])))) throw new InvalidDataException("old cloned identity still imported: " + imp);
        }
        Save(job, row, p, newName, type, newPartition);
        row["old_name"] = oldName; row["old_partition"] = oldPartition.ToString();
        row["exported_remap"] = exported; row["changes"] = rw.Changes; row["watched_strings"] = rw.Watched;
        row["unmapped_guid_fields"] = rw.GuidValues; row["unmapped_resource_refs"] = rw.ResourceValues;
    }

    // ---------------------------------------------------------------- RES: MeshSet (mirrors FET DuplicateLoadedMesh)
    static string Hex(byte[] b) => Convert.ToHexString(b).ToLowerInvariant();

    static Sdk.Resources.MeshSet LoadMesh(byte[] data, byte[] meta) => new Sdk.Resources.MeshSet(game, new MemoryStream(data), meta, true);

    static JsonObject MeshSummary(Sdk.Resources.MeshSet m)
    {
        var lods = new JsonArray();
        foreach (var lod in m.Lods)
        {
            var keys = new JsonArray();
            foreach (var s in lod.Subsets) keys.Add(s.ShaderExpressionInstanceKey.ToString());
            lods.Add(new JsonObject { ["name"] = lod.Name, ["chunk"] = lod.DataChunkId.ToString(), ["inline"] = lod.InlineDataLength, ["keys"] = keys });
        }
        var nh = typeof(Sdk.Resources.MeshSet).GetField("_nameHash", BindingFlags.NonPublic | BindingFlags.Instance)?.GetValue(m);
        return new JsonObject { ["name"] = m.Name, ["name_hash"] = nh?.ToString(), ["type"] = m.Type.ToString(), ["lods"] = lods };
    }

    static void MeshInfo(JsonObject job, JsonObject row)
    {
        var data = File.ReadAllBytes((string)job["input"]);
        var meta = Convert.FromHexString((string)job["meta"]);
        var m = LoadMesh(data, (byte[])meta.Clone());
        row["mesh"] = MeshSummary(m);
        // Round trip without changes must reproduce the native bytes and metadata.
        var again = m.ToStream(game).ToArray();
        row["roundtrip_identical"] = again.AsSpan().SequenceEqual(data) && m.Meta.AsSpan().SequenceEqual(meta);
    }

    static void MeshRes(JsonObject job, JsonObject row)
    {
        var data = File.ReadAllBytes((string)job["input"]);
        var meta = Convert.FromHexString((string)job["meta"]);
        var m = LoadMesh(data, (byte[])meta.Clone());
        var before = MeshSummary(m);
        string newName = (string)job["new_name"];
        m.SetNameInfo(newName, uint.Parse((string)job["name_hash"]));
        var chunks = job["chunks"]!.AsObject().ToDictionary(kv => Guid.Parse(kv.Key), kv => Guid.Parse((string)kv.Value));
        var keys = job["keys"]!.AsObject().ToDictionary(kv => ulong.Parse(kv.Key), kv => ulong.Parse((string)kv.Value));
        int i = 0;
        foreach (var lod in m.Lods)
        {
            lod.Name = $"{newName}_lod{i}";
            i++;
            if (lod.DataChunkId != Guid.Empty)
            {
                if (!chunks.TryGetValue(lod.DataChunkId, out var nc)) throw new InvalidDataException("no chunk mapping for LOD chunk " + lod.DataChunkId);
                lod.DataChunkId = nc;
            }
            foreach (var s in lod.Subsets)
                if (keys.TryGetValue(s.ShaderExpressionInstanceKey, out var nk)) s.ShaderExpressionInstanceKey = nk;
        }
        var output = m.ToStream(game).ToArray();
        var newMeta = (byte[])m.Meta.Clone();
        var check = LoadMesh(output, (byte[])newMeta.Clone());
        var after = MeshSummary(check);
        if (check.Name != newName.ToLowerInvariant()) throw new InvalidDataException("mesh name not written");
        var again = check.ToStream(game).ToArray();
        if (!again.AsSpan().SequenceEqual(output)) throw new InvalidDataException("mesh second write differs");
        var path = (string)job["output"];
        if (File.Exists(path)) throw new IOException("output exists: " + path);
        File.WriteAllBytes(path, output);
        row["output"] = path; row["sha256"] = Sha(output); row["meta"] = Hex(newMeta); row["before"] = before; row["after"] = after;
    }

    // ---------------------------------------------------------------- RES: texture header (mirrors FET DuplicateTexture)
    static void TextureInfo(JsonObject job, JsonObject row)
    {
        var data = File.ReadAllBytes((string)job["input"]);
        var h = Sdk.Resources.Texture.LoadHeader(game, new MemoryStream(data));
        row["chunk"] = h.StreamingChunkId.ToString(); row["name_hash"] = h.ResourceNameHash.ToString();
        row["roundtrip_identical"] = h.ToStream(game).ToArray().AsSpan().SequenceEqual(data);
    }

    static void TextureRes(JsonObject job, JsonObject row)
    {
        var data = File.ReadAllBytes((string)job["input"]);
        var h = Sdk.Resources.Texture.LoadHeader(game, new MemoryStream(data));
        if (!h.ToStream(game).ToArray().AsSpan().SequenceEqual(data)) throw new InvalidDataException("texture header does not round trip");
        var oldChunk = h.StreamingChunkId; var oldHash = h.ResourceNameHash;
        var expectChunk = Guid.Parse((string)job["old_chunk"]);
        if (oldChunk != expectChunk) throw new InvalidDataException($"texture chunk {oldChunk} != expected {expectChunk}");
        h.StreamingChunkId = Guid.Parse((string)job["chunk"]);
        h.ResourceNameHash = Sdk.Hash.Djb2Hash.HashStringLower64((string)job["new_name"]);
        var output = h.ToStream(game).ToArray();
        var check = Sdk.Resources.Texture.LoadHeader(game, new MemoryStream(output));
        if (check.StreamingChunkId != h.StreamingChunkId || check.ResourceNameHash != h.ResourceNameHash) throw new InvalidDataException("texture header not written");
        if (output.Length != data.Length) throw new InvalidDataException("texture header size changed");
        var path = (string)job["output"];
        if (File.Exists(path)) throw new IOException("output exists: " + path);
        File.WriteAllBytes(path, output);
        row["output"] = path; row["sha256"] = Sha(output);
        row["old_chunk"] = oldChunk.ToString(); row["chunk"] = check.StreamingChunkId.ToString();
        row["old_name_hash"] = oldHash.ToString(); row["name_hash"] = check.ResourceNameHash.ToString();
    }

    // ---------------------------------------------------------------- RES: shader block depot (mirrors FET PrepareExpressionShaderBundle)
    static Sdk.Resources.ShaderBlockDepotResource LoadSbd(byte[] data, byte[] meta) => new Sdk.Resources.ShaderBlockDepotResource(new ArraySegment<byte>(data), meta);

    static void SbdInfo(JsonObject job, JsonObject row)
    {
        var data = File.ReadAllBytes((string)job["input"]);
        var d = LoadSbd(data, Convert.FromHexString((string)job["meta"]));
        var keys = new JsonArray();
        var perEntry = new JsonObject();
        foreach (var e in d.Entries)
        {
            keys.Add(e.KeyHash.ToString());
            var refs = new JsonArray();
            foreach (var t in e.Block.TextureParameters) refs.Add($"{t.PartitionGuid}/{t.InstanceGuid}");
            perEntry[e.KeyHash.ToString()] = refs;
        }
        var tex = new JsonArray();
        foreach (var b in d.Blocks) foreach (var t in b.TextureParameters) tex.Add($"{t.PartitionGuid}/{t.InstanceGuid}");
        row["entries"] = keys; row["entry_texture_refs"] = perEntry; row["texture_refs"] = tex; row["blocks"] = d.Blocks.Count;
        row["roundtrip_identical"] = d.ToArray().AsSpan().SequenceEqual(data);
    }

    static void SbdAlias(JsonObject job, JsonObject row)
    {
        var data = File.ReadAllBytes((string)job["input"]);
        var source = LoadSbd(data, Convert.FromHexString((string)job["meta"]));
        var keyMap = job["keys"]!.AsObject().ToDictionary(kv => ulong.Parse(kv.Key), kv => ulong.Parse((string)kv.Value));
        foreach (var k in keyMap.Keys) if (!source.TryGetEntry(k, out _)) throw new InvalidDataException($"source depot has no key 0x{k:X16}");
        var inst = job["instances"]!.AsObject().ToDictionary(kv => Guid.Parse(kv.Key), kv => Guid.Parse((string)kv.Value));
        var part = job["partitions"]!.AsObject().ToDictionary(kv => Guid.Parse(kv.Key), kv => Guid.Parse((string)kv.Value));
        var depot = Sdk.Resources.ShaderBlockDepotResource.CreateEmpty().AppendEntriesFrom(source, (IReadOnlyDictionary<ulong, ulong>)keyMap);
        // FET's CheckCompleteShaderResourceRemaps: a texture reference must be fully mapped or not at all.
        int mapped = 0, kept = 0;
        foreach (var b in depot.Blocks)
            foreach (var t in b.TextureParameters)
            {
                bool i1 = inst.ContainsKey(t.InstanceGuid), p1 = part.ContainsKey(t.PartitionGuid);
                if (i1 != p1) throw new InvalidDataException($"texture parameter 0x{t.ParamHash:X16} has only one half of its GUID mapping");
                if (i1) mapped++; else kept++;
            }
        int remaps = depot.RemapTextureReferences((IReadOnlyDictionary<Guid, Guid>)inst, (IReadOnlyDictionary<Guid, Guid>)part);
        var output = depot.ToArray();
        var meta = (byte[])depot.Meta.Clone();
        var check = LoadSbd(output, (byte[])meta.Clone());
        var got = check.Entries.Select(e => e.KeyHash).OrderBy(x => x).ToList();
        var want = keyMap.Values.OrderBy(x => x).ToList();
        if (!got.SequenceEqual(want)) throw new InvalidDataException("alias depot keys differ from the key map");
        foreach (var e in check.Entries)
        {
            var src = keyMap.First(kv => kv.Value == e.KeyHash).Key;
            source.TryGetEntry(src, out var se);
            if (se.Block.Parameters.Count != e.Block.Parameters.Count) throw new InvalidDataException("block parameters changed");
        }
        foreach (var b in check.Blocks)
            foreach (var t in b.TextureParameters)
                if (inst.ContainsKey(t.InstanceGuid) || part.ContainsKey(t.PartitionGuid)) throw new InvalidDataException("old texture reference survived remap");
        var path = (string)job["output"];
        if (File.Exists(path)) throw new IOException("output exists: " + path);
        File.WriteAllBytes(path, output);
        row["output"] = path; row["sha256"] = Sha(output); row["meta"] = Hex(meta);
        row["entries"] = check.Entries.Count; row["texture_refs_remapped"] = remaps; row["texture_refs_mapped"] = mapped; row["texture_refs_kept"] = kept;
    }

    // ---------------------------------------------------------------- SubLevelMap
    static void SlmAdd(JsonObject job, JsonObject row)
    {
        var p = Read(File.ReadAllBytes((string)job["input"]));
        int key = (int)job["key"], model = (int)job["model_key"];
        string name = (string)job["name"];
        IList items = null; PropertyInfo keyProp = null, nameProp = null; object owner = null;
        foreach (var inst in p.Instances)
            foreach (var prop in Fields(inst.GetType()))
            {
                var t = prop.PropertyType;
                if (!t.IsGenericType || !typeof(IList).IsAssignableFrom(t)) continue;
                var et = t.GetGenericArguments()[0];
                var kp = et.GetProperty("KeyId"); var np = et.GetProperty("SubWorldName");
                if (kp == null || np == null) continue;
                if (items != null) throw new InvalidDataException("more than one SubLevelDefItem list");
                items = (IList)prop.GetValue(inst); keyProp = kp; nameProp = np; owner = inst;
            }
        if (items == null) throw new InvalidDataException("no SubLevelDefItem list");
        object modelItem = null; int count = items.Count;
        var keys = new List<int>();
        foreach (var it in items)
        {
            var k = (int)keyProp.GetValue(it);
            keys.Add(k);
            if (k == key) throw new InvalidDataException("key already present: " + key);
            if (string.Equals((string)nameProp.GetValue(it), name, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("name already present: " + name);
            if (k == model) { if (modelItem != null) throw new InvalidDataException("model key repeated"); modelItem = it; }
        }
        if (modelItem == null) throw new InvalidDataException("model key absent: " + model);
        var copy = DeepCopy(modelItem);
        keyProp.SetValue(copy, key); nameProp.SetValue(copy, name);
        items.Add(copy);
        row["items_before"] = count; row["items_after"] = items.Count;
        row["keys_sorted"] = keys.SequenceEqual(keys.OrderBy(x => x));
        row["model_item"] = DumpValue(modelItem, new Dictionary<object, int>(ReferenceEqualityComparer.Instance), 1);
        row["added_item"] = DumpValue(copy, new Dictionary<object, int>(ReferenceEqualityComparer.Instance), 1);
        Save(job, row, p, RootName(p), p.PrimaryInstance.GetType().Name, p.PartitionGuid);
    }

    // Deep copy of value objects; PointerRefs are kept (same targets), instances are not followed.
    static object DeepCopy(object v)
    {
        if (v == null || IsLeaf(v) || v is PointerRef || v is BoxedValueRef) return v;
        var t = v.GetType();
        if (v is IList list)
        {
            var nl = (IList)Activator.CreateInstance(t);
            foreach (var x in list) nl.Add(DeepCopy(x));
            return nl;
        }
        var copy = Activator.CreateInstance(t);
        foreach (var p in Fields(t)) p.SetValue(copy, DeepCopy(p.GetValue(v)));
        return copy;
    }

    // ---------------------------------------------------------------- stadium loader registration
    static void LoaderRegister(JsonObject job, JsonObject row)
    {
        var p = Read(File.ReadAllBytes((string)job["input"]));
        string model = (string)job["model"], name = (string)job["name"];
        var newGuid = Guid.Parse((string)job["instance_guid"]);
        var all = p.Instances.ToList();
        IEbxInstance modelRef = null;
        foreach (var inst in all)
        {
            if (inst.GetType().Name != "SubWorldReferenceObjectData") continue;
            var bn = (string)inst.GetType().GetProperty("BundleName").GetValue(inst);
            if (string.Equals(bn, name, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("new bundle already referenced");
            if (string.Equals(bn, model, StringComparison.OrdinalIgnoreCase)) { if (modelRef != null) throw new InvalidDataException("model repeated"); modelRef = inst; }
        }
        if (modelRef == null) throw new InvalidDataException("model reference absent");
        // DataBusPeer flags: the low 25 bits are the peer UniqueId (unique per loader).
        var flagsProp = modelRef.GetType().GetProperty("Flags");
        var used = new HashSet<uint>();
        foreach (var inst in all) { var fp = inst.GetType().GetProperty("Flags"); if (fp != null && fp.PropertyType == typeof(uint)) used.Add((uint)fp.GetValue(inst) & 0x1FFFFFF); }
        var copy = (IEbxInstance)DeepCopy(modelRef);
        copy.GetType().GetProperty("BundleName").SetValue(copy, name);
        var modelFlags = (uint)flagsProp.GetValue(modelRef);
        uint uid = BitConverter.ToUInt32(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(RootName(p) + "|" + name)), 0) & 0x1FFFFFF;
        while (uid == 0 || used.Contains(uid)) uid = (uid + 1) & 0x1FFFFFF;
        flagsProp.SetValue(copy, (modelFlags & ~0x1FFFFFFu) | uid);
        var modelId = modelRef.InstanceId;
        copy.InstanceId = modelId.IsExported ? new EbxInstanceId(newGuid, -1, true) : new EbxInstanceId(-1);
        p.AddInstance(copy);
        // Every list of pointers that holds the model reference receives the new one at its end.
        var appended = new JsonArray();
        var connections = new JsonArray();
        foreach (var inst in all)
            foreach (var prop in Fields(inst.GetType()))
                ScanLists(prop.GetValue(inst), inst.GetType().Name + "." + prop.Name, modelRef, copy, appended, connections);
        row["model_flags"] = $"0x{modelFlags:X8}"; row["new_flags"] = $"0x{(modelFlags & ~0x1FFFFFFu) | uid:X8}";
        row["model_exported"] = modelId.IsExported; row["appended_lists"] = appended; row["copied_connections"] = connections;
        Save(job, row, p, RootName(p), p.PrimaryInstance.GetType().Name, p.PartitionGuid);
    }

    static void ScanLists(object v, string path, IEbxInstance model, IEbxInstance copy, JsonArray appended, JsonArray connections)
    {
        if (v is not IList list) { if (v != null && !IsLeaf(v) && v is not PointerRef && v is not IEbxInstance && IsFrostbite(v.GetType())) foreach (var p in Fields(v.GetType())) ScanLists(p.GetValue(v), path + "." + p.Name, model, copy, appended, connections); return; }
        var et = list.GetType().GetGenericArguments()[0];
        if (et == typeof(PointerRef))
        {
            int hits = 0;
            foreach (PointerRef pr in list) if (pr.Type == PointerRefType.Internal && ReferenceEquals(pr.Internal, model)) hits++;
            if (hits > 1) throw new InvalidDataException(path + ": model listed twice");
            if (hits == 1) { list.Add(new PointerRef(copy)); appended.Add(path + $" ({list.Count - 1} -> {list.Count})"); }
            return;
        }
        // Connection-like structs: copy each element whose pointer fields reference the model.
        int n = list.Count;
        for (int i = 0; i < n; i++)
        {
            var item = list[i];
            if (item == null || IsLeaf(item)) continue;
            var ptrs = Fields(item.GetType()).Where(f => f.PropertyType == typeof(PointerRef)).ToList();
            bool refers = ptrs.Any(f => { var pr = (PointerRef)f.GetValue(item); return pr.Type == PointerRefType.Internal && ReferenceEquals(pr.Internal, model); });
            if (!refers)
            {
                if (IsFrostbite(item.GetType())) foreach (var f in Fields(item.GetType())) ScanLists(f.GetValue(item), path + $"[{i}]." + f.Name, model, copy, appended, connections);
                continue;
            }
            var dup = DeepCopy(item);
            foreach (var f in ptrs) { var pr = (PointerRef)f.GetValue(dup); if (pr.Type == PointerRefType.Internal && ReferenceEquals(pr.Internal, model)) f.SetValue(dup, new PointerRef(copy)); }
            list.Add(dup);
            connections.Add(path + $"[{i}] -> [{list.Count - 1}] " + DumpValue(dup, new Dictionary<object, int>(ReferenceEqualityComparer.Instance), 1).ToJsonString());
        }
    }

    // ---------------------------------------------------------------- hashes and file system
    // Bundle name hash as AssetManager.AddBundle computes it; chunk H32 as AddUnmodifiedAssetToBundle does.
    static void Hashes(JsonObject job, JsonObject row)
    {
        var result = new JsonArray();
        foreach (var n in job["names"]!.AsArray())
        {
            var name = (string)n;
            var lower = name.ToLowerInvariant();
            result.Add(new JsonObject
            {
                ["name"] = name,
                ["xxh3_utf16_lower"] = System.IO.Hashing.XxHash3.HashToUInt64(System.Runtime.InteropServices.MemoryMarshal.AsBytes(lower.AsSpan())).ToString(),
                ["djb2_lower64"] = Sdk.Hash.Djb2Hash.HashStringLower64(name).ToString(),
                ["djb2_32"] = Sdk.Hash.Djb2Hash.HashString32(name).ToString(),
                ["fnv1_lower64"] = Sdk.Hash.FnvHash.HashString64Lower(name).ToString(),
                // AssetManager.GenerateDeterministicChunkGuid and the shader depot names hash the exact/lowered UTF-16 text.
                ["xxh64_utf16_lower"] = System.IO.Hashing.XxHash64.HashToUInt64(System.Runtime.InteropServices.MemoryMarshal.AsBytes(lower.AsSpan())).ToString(),
                ["xxh3_utf16_exact"] = System.IO.Hashing.XxHash3.HashToUInt64(System.Runtime.InteropServices.MemoryMarshal.AsBytes(name.AsSpan())).ToString()
            });
        }
        row["hashes"] = result;
    }

    // FET PrepareExpressionShaderBundle: newKey = XxHash3(LE(XxHash3(UTF-16 depot name)) || LE(sourceKey)).
    static void AliasKeys(JsonObject job, JsonObject row)
    {
        var depot = (string)job["depot_name"];
        Span<byte> span = stackalloc byte[16];
        System.Buffers.Binary.BinaryPrimitives.WriteUInt64LittleEndian(span, System.IO.Hashing.XxHash3.HashToUInt64(System.Runtime.InteropServices.MemoryMarshal.AsBytes(depot.AsSpan())));
        var map = new JsonObject();
        foreach (var k in job["keys"]!.AsArray())
        {
            var key = ulong.Parse((string)k);
            System.Buffers.Binary.BinaryPrimitives.WriteUInt64LittleEndian(span.Slice(8), key);
            map[key.ToString()] = System.IO.Hashing.XxHash3.HashToUInt64(span).ToString();
        }
        row["depot_name"] = depot; row["keys"] = map;
    }

    static void FsInfo(JsonObject job, JsonObject row)
    {
        var sb = new JsonArray();
        for (int i = 0; i < fs.SuperBundles.Count; i++)
            sb.Add(new JsonObject { ["index"] = i, ["name"] = fs.SuperBundles[i].Name, ["hash"] = fs.SuperBundles[i].NameHash, ["installchunk"] = fs.SuperBundles[i].InstallChunkPersistentIndex });
        row["superbundles"] = sb;
        var cat = new JsonObject();
        foreach (var kv in fs.Catalogs) cat[kv.Key.ToString()] = kv.Value;
        row["catalogs"] = cat;
        row["head"] = fs.GetType().GetProperty("Head")?.GetValue(fs)?.ToString();
    }

    // ---------------------------------------------------------------- graph snapshot
    sealed class Snapshot
    {
        public int Instances, Exports, Internal, External;
        public List<string> Imports = new();
        public string Key;

        public static Snapshot Of(EbxPartition p)
        {
            var s = new Snapshot();
            var set = new HashSet<object>(p.Instances, ReferenceEqualityComparer.Instance);
            var visited = new HashSet<object>(ReferenceEqualityComparer.Instance);
            var ext = new SortedDictionary<string, int>(StringComparer.Ordinal);
            void Visit(object v)
            {
                if (v == null || v is string) return;
                if (v is PointerRef pr)
                {
                    if (pr.Type == PointerRefType.Internal) { s.Internal++; if (pr.Internal == null || !set.Contains(pr.Internal)) throw new InvalidDataException("dangling internal pointer"); }
                    else if (pr.Type == PointerRefType.External) { s.External++; var k = pr.External.PartitionGuid + "/" + pr.External.InstanceGuid; ext[k] = ext.GetValueOrDefault(k) + 1; }
                    return;
                }
                if (IsLeaf(v)) return;
                if (!v.GetType().IsValueType && !visited.Add(v)) return;
                if (v is IList l) { foreach (var x in l) Visit(x); return; }
                if (v is BoxedValueRef b) { Visit(b.Value); return; }
                if (!IsFrostbite(v.GetType())) return;
                foreach (var f in Fields(v.GetType())) Visit(f.GetValue(v));
            }
            foreach (var inst in p.Instances) { s.Instances++; if (inst.InstanceId.IsExported) s.Exports++; Visit(inst); }
            s.Imports = ext.Keys.ToList();
            var exports = string.Join(",", p.ExportedInstances.Select(x => x.InstanceId.InstanceGuid.ToString()).Order(StringComparer.Ordinal));
            s.Key = $"{s.Instances}|{s.Exports}|{s.Internal}|{s.External}|{JsonSerializer.Serialize(ext)}|{exports}";
            return s;
        }
    }
}
