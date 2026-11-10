// Generic EBX editing on the SDK object model: clone instances, set fields by path, replace lists, remove
// instances, and the crowd point-cloud replacement. Every written partition is re-read and written again
// (both writes must match), checked for dangling internal pointers, and kept in the FC27 instance order:
// exported instances first, the primary at 0 and the other exported ones sorted by GUID (memcmp of its 16
// bytes). The game finds an exported instance by binary search over that order, so an exported clone
// appended out of order is never found (Morumbi v1/v2 crashed at kick-off on such a null MeshMaterial).
using System.Collections;
using System.Globalization;
using System.Reflection;
using System.Text.Json.Nodes;
using Sdk.Ebx;
using Sdk.Ebx.Serialization;

static partial class Program
{
    static EbxPartition ReadEbx(byte[] bytes)
    {
        using var source = new MemoryStream(bytes);
        using var reader = BaseEbxPartitionReader.CreateReader(source, fs, game.FrostbiteVersion);
        return reader.ReadPartition<EbxPartition>();
    }

    static byte[] WriteEbx(EbxPartition p)
    {
        using var destination = new MemoryStream();
        using (var writer = BaseEbxPartitionWriter.CreateWriter(destination, fs, game.FrostbiteVersion, leaveOpen: true)) writer.WritePartition(p);
        return destination.ToArray();
    }

    static int CompareGuid(Guid a, Guid b) => a.ToByteArray().AsSpan().SequenceCompareTo(b.ToByteArray());

    // Puts the instances in the FC27 order (see the header); returns false when they already were.
    static bool SortExported(EbxPartition p)
    {
        var prim = p.PrimaryInstance;
        var all = p.Instances.ToList();
        var want = new List<IEbxInstance> { prim };
        var exported = all.Where(i => i != prim && i.InstanceId.IsExported).ToList();
        exported.Sort((a, b) => CompareGuid(a.InstanceId.InstanceGuid, b.InstanceId.InstanceGuid));
        want.AddRange(exported);
        want.AddRange(all.Where(i => i != prim && !i.InstanceId.IsExported));
        if (want.SequenceEqual(all, ReferenceEqualityComparer.Instance)) return false;
        foreach (var i in all) if (i != prim) p.RemoveInstance(i);
        foreach (var i in want.Skip(1)) p.AddInstance(i);
        if (!p.Instances.SequenceEqual(want, ReferenceEqualityComparer.Instance)) throw new InvalidDataException("instance reorder did not apply");
        return true;
    }

    static void CheckExportedOrder(EbxPartition p)
    {
        var all = p.Instances.ToList();
        if (all.Count == 0 || all[0] != p.PrimaryInstance) throw new InvalidDataException("primary instance is not first");
        int n = all.Count(i => i.InstanceId.IsExported);
        for (int k = 0; k < n; k++)
            if (!all[k].InstanceId.IsExported) throw new InvalidDataException("exported instances are not first");
        for (int k = 2; k < n; k++)
            if (CompareGuid(all[k - 1].InstanceId.InstanceGuid, all[k].InstanceId.InstanceGuid) >= 0)
                throw new InvalidDataException("exported instances are not sorted by GUID at " + k);
    }

    static readonly Dictionary<Type, PropertyInfo[]> ebxProps = new();

    static PropertyInfo[] EbxFields(Type t)
    {
        if (ebxProps.TryGetValue(t, out var cached)) return cached;
        var list = new List<PropertyInfo>();
        for (var x = t; x != null && x != typeof(object) && x != typeof(ValueType); x = x.BaseType)
            foreach (var p in x.GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly))
                if (p.CanRead && p.CanWrite && p.GetIndexParameters().Length == 0 && p.GetCustomAttributes().Any(a => a.GetType().Name == "NameHashAttribute"))
                    list.Add(p);
        return ebxProps[t] = list.ToArray();
    }

    static bool EbxLeaf(object v) => v is string || v is Guid || v is decimal || v is ResourceRef || v is FileRef || v is TypeRef
        || v is EbxInstanceId || v.GetType().IsPrimitive || v.GetType().IsEnum;

    static object EbxCopy(object v)
    {
        if (v == null || EbxLeaf(v) || v is PointerRef || v is BoxedValueRef) return v;
        var t = v.GetType();
        if (v is IList list)
        {
            var nl = (IList)Activator.CreateInstance(t);
            foreach (var x in list) nl.Add(EbxCopy(x));
            return nl;
        }
        var copy = Activator.CreateInstance(t);
        foreach (var p in EbxFields(t)) p.SetValue(copy, EbxCopy(p.GetValue(v)));
        return copy;
    }

    sealed class EbxSession
    {
        public EbxPartition P;
        public Dictionary<string, IEbxInstance> Tags = new();
        public JsonArray Log = new();

        public IEbxInstance Ref(JsonNode r)
        {
            var o = r!.AsObject();
            if (o.ContainsKey("tag")) return Tags[(string)o["tag"]];
            if (o.ContainsKey("primary")) return P.PrimaryInstance;
            if (o.ContainsKey("index")) return P.Instances.ElementAt((int)o["index"]);
            var g = Guid.Parse((string)o["guid"]);
            var hits = P.Instances.Where(i => i.InstanceId.InstanceGuid == g).ToList();
            if (hits.Count != 1) throw new InvalidDataException($"instance {g}: {hits.Count} matches");
            return hits[0];
        }
    }

    static object MakeValue(EbxSession s, JsonNode spec, Type t)
    {
        if (spec is JsonValue jv)
        {
            if (t == typeof(string)) return (string)jv;
            if (t == typeof(bool)) return (bool)jv;
            if (t == typeof(float)) return (float)(double)jv;
            if (t == typeof(int)) return (int)jv;
            if (t == typeof(uint)) return uint.Parse(jv.ToString(), CultureInfo.InvariantCulture);
            if (t == typeof(ulong)) return ulong.Parse(jv.ToString(), CultureInfo.InvariantCulture);
            if (t == typeof(byte)) return (byte)(int)jv;
            if (t.IsEnum) return Enum.Parse(t, (string)jv);
            if (t == typeof(Guid)) { var gs = (string)jv; return Guid.Parse(gs.StartsWith("guid:") ? gs[5..] : gs); }
            if (t.IsPrimitive) return Convert.ChangeType(jv.ToString(), t, CultureInfo.InvariantCulture);
        }
        var o = spec!.AsObject();
        if (o.ContainsKey("ext")) { var a = o["ext"]!.AsArray(); return new PointerRef(new EbxImportReference { PartitionGuid = Guid.Parse((string)a[0]), InstanceGuid = Guid.Parse((string)a[1]) }); }
        if (o.ContainsKey("int")) return new PointerRef(s.Ref(o["int"]));
        if (o.ContainsKey("null")) return new PointerRef();
        if (o.ContainsKey("res")) return new ResourceRef(ulong.Parse((string)o["res"], CultureInfo.InvariantCulture));
        if (o.ContainsKey("copy_of")) return EbxCopy(s.Ref(o["copy_of"]));
        if (o.ContainsKey("fields"))
        {
            // A struct or object of type t with the given fields set (others default).
            var obj = Activator.CreateInstance(t);
            foreach (var kv in o["fields"]!.AsObject())
            {
                var p = t.GetProperty(kv.Key) ?? throw new InvalidDataException($"no field {kv.Key} on {t.Name}");
                p.SetValue(obj, MakeValue(s, kv.Value, p.PropertyType));
            }
            return obj;
        }
        if (o.ContainsKey("like"))
        {
            // Deep copy of an existing value at a path, then field overrides.
            var baseValue = EbxCopy(GetAt(s.Ref(o["like"]!["from"]), (string)o["like"]!["path"]));
            if (o["set"] is JsonObject sets)
                foreach (var kv in sets)
                {
                    var p = baseValue.GetType().GetProperty(kv.Key) ?? throw new InvalidDataException("no field " + kv.Key);
                    p.SetValue(baseValue, MakeValue(s, kv.Value, p.PropertyType));
                }
            return baseValue;
        }
        if (o.ContainsKey("vec3"))
        {
            var a = o["vec3"]!.AsArray();
            var v = Activator.CreateInstance(t);
            t.GetProperty("x")!.SetValue(v, (float)a[0]); t.GetProperty("y")!.SetValue(v, (float)a[1]); t.GetProperty("z")!.SetValue(v, (float)a[2]);
            return v;
        }
        throw new InvalidDataException("unknown value spec " + spec.ToJsonString());
    }

    // Sets a value at a path; structs met on the way are modified as boxed copies and written back to their owner.
    static void SetAt(EbxSession s, IEbxInstance target, string path, JsonNode spec)
    {
        var segs = path.Split('.');
        SetRec(s, target, segs, 0, spec);
    }

    static object SetRec(EbxSession s, object cur, string[] segs, int k, JsonNode spec)
    {
        string seg = segs[k]; int idx = -1;
        int br = seg.IndexOf('[');
        if (br >= 0) { idx = int.Parse(seg[(br + 1)..seg.IndexOf(']')]); seg = seg[..br]; }
        var prop = cur.GetType().GetProperty(seg) ?? throw new InvalidDataException($"no field {seg} on {cur.GetType().Name}");
        bool last = k == segs.Length - 1;
        if (idx < 0)
        {
            object v = last ? MakeValue(s, spec, prop.PropertyType) : SetRec(s, prop.GetValue(cur), segs, k + 1, spec);
            prop.SetValue(cur, v);
        }
        else
        {
            var list = (IList)prop.GetValue(cur);
            var et = list.GetType().GetGenericArguments()[0];
            list[idx] = last ? MakeValue(s, spec, et) : SetRec(s, list[idx], segs, k + 1, spec);
        }
        return cur;
    }

    static object GetAt(object cur, string path)
    {
        foreach (var raw in path.Split('.'))
        {
            string seg = raw; int idx = -1;
            int br = seg.IndexOf('[');
            if (br >= 0) { idx = int.Parse(seg[(br + 1)..seg.IndexOf(']')]); seg = seg[..br]; }
            var prop = cur.GetType().GetProperty(seg) ?? throw new InvalidDataException($"no field {seg} on {cur.GetType().Name}");
            cur = prop.GetValue(cur);
            if (idx >= 0) cur = ((IList)cur)[idx];
        }
        return cur;
    }

    static void EbxOps(JsonObject job, JsonObject row)
    {
        var input = File.ReadAllBytes((string)job["input"]);
        var s = new EbxSession { P = ReadEbx(input) };
        var p = s.P;
        string expectName = (string)job["expect_name"];
        string rootName = p.PrimaryInstance.GetType().GetProperty("Name")?.GetValue(p.PrimaryInstance) as string;
        if (expectName != null && rootName != expectName) throw new InvalidDataException($"root '{rootName}' != '{expectName}'");
        int before = p.Instances.Count();
        foreach (var node in job["ops"]!.AsArray())
        {
            var op = node!.AsObject();
            switch ((string)op["op"])
            {
                case "clone":
                {
                    var src = s.Ref(op["source"]);
                    var copy = (IEbxInstance)EbxCopy(src);
                    bool exported = op.ContainsKey("exported") ? (bool)op["exported"] : src.InstanceId.IsExported;
                    copy.InstanceId = exported ? new EbxInstanceId(Guid.Parse((string)op["guid"]), -1, true) : new EbxInstanceId(-1);
                    p.AddInstance(copy);
                    s.Tags[(string)op["tag"]] = copy;
                    break;
                }
                case "set":
                    SetAt(s, s.Ref(op["target"]), (string)op["path"], op["value"]);
                    break;
                case "list_set":
                {
                    var list = (IList)GetAt(s.Ref(op["target"]), (string)op["path"]);
                    var et = list.GetType().GetGenericArguments()[0];
                    list.Clear();
                    foreach (var it in op["items"]!.AsArray()) list.Add(MakeValue(s, it, et));
                    break;
                }
                case "list_append":
                {
                    var list = (IList)GetAt(s.Ref(op["target"]), (string)op["path"]);
                    var et = list.GetType().GetGenericArguments()[0];
                    foreach (var it in op["items"]!.AsArray()) list.Add(MakeValue(s, it, et));
                    break;
                }
                case "list_keep":
                {
                    // Keeps only the given indices (in the given order) of a list.
                    var list = (IList)GetAt(s.Ref(op["target"]), (string)op["path"]);
                    var keep = op["indices"]!.AsArray().Select(x => list[(int)x]).ToList();
                    list.Clear();
                    foreach (var x in keep) list.Add(x);
                    break;
                }
                case "remove":
                    p.RemoveInstance(s.Ref(op["target"]));
                    break;
                case "remove_unreferenced":
                {
                    // Instances that no other instance points to any more (after list edits), of the given types.
                    var types = op["types"]!.AsArray().Select(x => (string)x).ToHashSet();
                    while (true)
                    {
                        var refd = new HashSet<object>(ReferenceEqualityComparer.Instance);
                        foreach (var inst in p.Instances) CollectInternal(inst, refd, new HashSet<object>(ReferenceEqualityComparer.Instance), true);
                        var dead = p.Instances.Where(i => i != p.PrimaryInstance && !refd.Contains(i) && types.Contains(i.GetType().Name) && !i.InstanceId.IsExported).ToList();
                        if (dead.Count == 0) break;
                        foreach (var d in dead) p.RemoveInstance(d);
                    }
                    break;
                }
                case "partition":
                    p.SetPartitionGuid(Guid.Parse((string)op["guid"]));
                    break;
                case "primary_guid":
                {
                    var prim = p.PrimaryInstance;
                    if (!prim.InstanceId.IsExported) throw new InvalidDataException("primary instance is not exported");
                    prim.InstanceId = new EbxInstanceId(Guid.Parse((string)op["guid"]), prim.InstanceId.Index, true);
                    break;
                }
                case "crowd":
                    CrowdReplace(s, op);
                    break;
                default:
                    throw new InvalidDataException("unknown op " + (string)op["op"]);
            }
            s.Log.Add((string)op["op"]);
        }
        bool reordered = SortExported(p);
        // Dangling internal pointers would crash the reader; check before writing.
        var all = new HashSet<object>(p.Instances, ReferenceEqualityComparer.Instance);
        foreach (var inst in p.Instances)
        {
            var refd = new HashSet<object>(ReferenceEqualityComparer.Instance);
            CollectInternal(inst, refd, new HashSet<object>(ReferenceEqualityComparer.Instance), false);
            foreach (var r in refd) if (!all.Contains(r)) throw new InvalidDataException("dangling internal pointer from " + inst.GetType().Name);
        }
        var first = WriteEbx(p);
        var again = ReadEbx(first);
        var second = WriteEbx(again);
        if (!first.AsSpan().SequenceEqual(second)) throw new InvalidDataException("second write differs from first write");
        CheckExportedOrder(again);
        string newRoot = again.PrimaryInstance.GetType().GetProperty("Name")?.GetValue(again.PrimaryInstance) as string;
        if (job["expect_new_name"] is JsonValue en && (string)en != newRoot) throw new InvalidDataException($"new root '{newRoot}' != '{(string)en}'");
        var output = (string)job["output"];
        if (File.Exists(output)) throw new IOException("output exists: " + output);
        File.WriteAllBytes(output, first);
        var imports = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var inst in again.Instances) CollectExternal(inst, imports, new HashSet<object>(ReferenceEqualityComparer.Instance));
        row["output"] = output; row["sha256"] = Sha(first); row["bytes"] = first.Length; row["root"] = newRoot;
        row["partition"] = again.PartitionGuid.ToString(); row["type"] = again.PrimaryInstance.GetType().Name;
        row["instances_before"] = before; row["instances_after"] = again.Instances.Count(); row["reordered"] = reordered;
        row["exported"] = new JsonArray(again.Instances.Where(i => i.InstanceId.IsExported).Select(i => (JsonNode)i.InstanceId.InstanceGuid.ToString()).ToArray());
        row["imports"] = new JsonArray(imports.Select(x => (JsonNode)x).ToArray());
        row["ops"] = s.Log;
    }

    static void CollectInternal(object v, HashSet<object> refd, HashSet<object> seen, bool skipSelfRoot)
    {
        if (v == null || v is string || EbxLeaf(v)) return;
        if (v is PointerRef pr) { if (pr.Type == PointerRefType.Internal && pr.Internal != null) refd.Add(pr.Internal); return; }
        if (!v.GetType().IsValueType && !seen.Add(v)) return;
        if (v is IList l) { foreach (var x in l) CollectInternal(x, refd, seen, skipSelfRoot); return; }
        if (v is BoxedValueRef b) { CollectInternal(b.Value, refd, seen, skipSelfRoot); return; }
        if (v.GetType().Namespace?.StartsWith("Frostbite", StringComparison.Ordinal) != true) return;
        foreach (var p in EbxFields(v.GetType())) CollectInternal(p.GetValue(v), refd, seen, skipSelfRoot);
    }

    static void CollectExternal(object v, SortedSet<string> ext, HashSet<object> seen)
    {
        if (v == null || v is string || EbxLeaf(v)) return;
        if (v is PointerRef pr) { if (pr.Type == PointerRefType.External) ext.Add(pr.External.PartitionGuid + "/" + pr.External.InstanceGuid); return; }
        if (!v.GetType().IsValueType && !seen.Add(v)) return;
        if (v is IList l) { foreach (var x in l) CollectExternal(x, ext, seen); return; }
        if (v is BoxedValueRef b) { CollectExternal(b.Value, ext, seen); return; }
        if (v.GetType().Namespace?.StartsWith("Frostbite", StringComparison.Ordinal) != true) return;
        foreach (var p in EbxFields(v.GetType())) CollectExternal(p.GetValue(v), ext, seen);
    }

    // ---------------------------------------------------------------- crowd point cloud
    // Replaces the seats of a CrowdPlacementPointCloudDataAsset: positions and every user-data map, from a
    // little-endian file of records (x, y, z, orientation f32; card u32; seat colour u32; tier u8 + 3 pad;
    // neutral, ultra, fifty, attendance f32).
    static void CrowdReplace(EbxSession s, JsonObject op)
    {
        var asset = s.P.PrimaryInstance;
        if (asset.GetType().Name != "CrowdPlacementPointCloudDataAsset") throw new InvalidDataException("not a crowd point cloud");
        var raw = File.ReadAllBytes((string)op["data"]);
        if (Sha(raw) != (string)op["sha256"]) throw new InvalidDataException("crowd data hash mismatch");
        const int rec = 44;
        int n = raw.Length / rec;
        if (n * rec != raw.Length || n == 0) throw new InvalidDataException("crowd data size");
        var dataList = (IList)asset.GetType().GetProperty("Data")!.GetValue(asset);
        var itemType = dataList.GetType().GetGenericArguments()[0];
        dataList.Clear();
        var posProp = itemType.GetProperty("Position")!;
        for (int i = 0; i < n; i++)
        {
            var item = Activator.CreateInstance(itemType);
            var v = Activator.CreateInstance(posProp.PropertyType);
            posProp.PropertyType.GetProperty("x")!.SetValue(v, BitConverter.ToSingle(raw, i * rec));
            posProp.PropertyType.GetProperty("y")!.SetValue(v, BitConverter.ToSingle(raw, i * rec + 4));
            posProp.PropertyType.GetProperty("z")!.SetValue(v, BitConverter.ToSingle(raw, i * rec + 8));
            posProp.SetValue(item, v);
            dataList.Add(item);
        }
        var maps = new Dictionary<string, object>();
        foreach (var inst in s.P.Instances)
        {
            var np = inst.GetType().GetProperty("Name");
            if (inst.GetType().Name.StartsWith("UserData") && np != null) maps[(string)np.GetValue(inst)] = inst;
        }
        void Fill(string name, Func<int, object> val)
        {
            var m = maps[name];
            var list = (IList)m.GetType().GetProperty("val")!.GetValue(m);
            list.Clear();
            for (int i = 0; i < n; i++) list.Add(val(i));
        }
        Fill("Orientation", i => BitConverter.ToSingle(raw, i * rec + 12));
        Fill("CardColor", i => BitConverter.ToUInt32(raw, i * rec + 16));
        Fill("SeatColor", i => BitConverter.ToUInt32(raw, i * rec + 20));
        Fill("SeatTier", i => raw[i * rec + 24]);
        Fill("HomeAwayNeutral", i => BitConverter.ToSingle(raw, i * rec + 28));
        Fill("HomeAwayUltra", i => BitConverter.ToSingle(raw, i * rec + 32));
        Fill("HomeAwayFiftyFifty", i => BitConverter.ToSingle(raw, i * rec + 36));
        Fill("Attendance", i => BitConverter.ToSingle(raw, i * rec + 40));
        if (maps.Count != 8) throw new InvalidDataException("expected 8 user data maps, found " + maps.Count);
        s.Log.Add($"crowd seats {n}");
    }
}

static partial class Program
{
    // Plain JSON dump of a partition (same shape as StadiumTool's dump), for partitions read from a project.
    static void EbxDump(JsonObject job, JsonObject row)
    {
        var p = ReadEbx(File.ReadAllBytes((string)job["input"]));
        var index = new Dictionary<object, int>(ReferenceEqualityComparer.Instance);
        int i = 0;
        foreach (var inst in p.Instances) index[inst] = i++;
        var instances = new JsonArray();
        foreach (var inst in p.Instances)
            instances.Add(new JsonObject { ["index"] = index[inst], ["guid"] = inst.InstanceId.InstanceGuid.ToString(), ["exported"] = inst.InstanceId.IsExported,
                ["type"] = inst.GetType().FullName, ["fields"] = DumpNode(inst, index, 0) });
        var doc = new JsonObject { ["partition"] = p.PartitionGuid.ToString(), ["name"] = p.PrimaryInstance.GetType().GetProperty("Name")?.GetValue(p.PrimaryInstance) as string,
            ["type"] = p.PrimaryInstance.GetType().Name, ["instances"] = instances };
        var output = (string)job["output"];
        if (File.Exists(output)) throw new IOException("output exists: " + output);
        File.WriteAllText(output, doc.ToJsonString(Pretty));
        row["output"] = output; row["instances"] = i;
    }

    static JsonNode DumpNode(object v, Dictionary<object, int> index, int depth)
    {
        if (v == null) return null;
        if (depth > 40) return "<deep>";
        switch (v)
        {
            case string s: return s;
            case bool b: return b;
            case float f: return float.IsFinite(f) ? f : f.ToString(CultureInfo.InvariantCulture);
            case double d: return d;
            case Guid g: return "guid:" + g;
            case ResourceRef r: return "res:" + ((ulong)typeof(ResourceRef).GetField("_resourceId", BindingFlags.NonPublic | BindingFlags.Instance)?.GetValue(r)).ToString("X16");
            case PointerRef pr:
                return pr.Type switch
                {
                    PointerRefType.Null => "ptr:null",
                    PointerRefType.External => $"ptr:ext:{pr.External.PartitionGuid}/{pr.External.InstanceGuid}",
                    _ => pr.Internal != null && index.TryGetValue(pr.Internal, out var ii) ? $"ptr:int:{ii}" : "ptr:int:?"
                };
        }
        var t = v.GetType();
        if (t.IsEnum) return v.ToString();
        if (t.IsPrimitive) return JsonValue.Create(Convert.ToDouble(v, CultureInfo.InvariantCulture));
        if (v is IList l) { var a = new JsonArray(); foreach (var x in l) a.Add(DumpNode(x, index, depth + 1)); return a; }
        if (v is BoxedValueRef bv) return new JsonObject { ["boxed"] = DumpNode(bv.Value, index, depth + 1) };
        var o = new JsonObject();
        foreach (var p in EbxFields(t)) o[p.Name] = DumpNode(p.GetValue(v), index, depth + 1);
        if (!(v is IEbxInstance)) o["$type"] = t.Name;
        return o;
    }
}
