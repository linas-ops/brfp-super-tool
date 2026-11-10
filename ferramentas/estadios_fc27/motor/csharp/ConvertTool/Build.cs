// Builders for the FIFA 16 -> FC27 conversion: MeshSet with new subsets, new textures, shader depot entries.
using System.Buffers.Binary;
using System.Numerics;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using Sdk.Compression;
using Sdk.Reflection;
using Sdk.Resources;

static partial class Program
{
    // ---------------------------------------------------------------- shared
    static readonly MethodInfo MemberwiseCloneMethod = typeof(object).GetMethod("MemberwiseClone", BindingFlags.NonPublic | BindingFlags.Instance);
    static readonly Dictionary<string, MeshSet> templateCache = new();

    static MeshSet Template(string path, string meta)
    {
        var key = path + "|" + meta;
        if (!templateCache.TryGetValue(key, out var m)) templateCache[key] = m = LoadMesh(File.ReadAllBytes(path), Convert.FromHexString(meta));
        return m;
    }

    // Frostbite string hash used for MeshSubset.MaterialNameHash: h = (h * 33) ^ c over the lower-case name.
    static uint FbHash(string s)
    {
        uint h = 5381;
        foreach (var c in s.ToLowerInvariant()) h = (h * 33) ^ c;
        return h;
    }

    static AxisAlignedBox MakeBox(JsonArray b) => new AxisAlignedBox
    {
        Min = new Vec3 { X = (float)b[0], Y = (float)b[1], Z = (float)b[2] },
        Max = new Vec3 { X = (float)b[3], Y = (float)b[4], Z = (float)b[5] }
    };

    // Port of FET Editor.Lib TangentSpaceCompression.PackAxisAngleFrostbite (AxisAngle_Compact, UByte4N).
    static Vector4 PackAxisAngle(Vector3 tangent, Vector3 binormal, Vector3 normal)
    {
        Vector3 n = Vector3.Normalize(normal);
        Vector3 t = Vector3.Normalize(tangent - n * Vector3.Dot(n, tangent));
        uint flip = Vector3.Dot(Vector3.Cross(n, t), binormal) < 0f ? 8u : 0u;
        float ax = MathF.Abs(n.X), ay = MathF.Abs(n.Y), az = MathF.Abs(n.Z);
        int g = !(ax > ay) ? (!(ay > az) ? 2 : 1) : (!(ax > az) ? 2 : 0);
        uint face = (uint)(g * 2) + (n[g] < 0f ? 1u : 0u);
        Vector3 a = g == 1 ? Vector3.Normalize(new Vector3(-n.Y, n.X, 0f)) : Vector3.Normalize(new Vector3(n.Z, 0f, -n.X));
        Vector3 b = Vector3.Cross(n, a);
        float ang = MathF.Atan2(Vector3.Dot(b, t), Vector3.Dot(a, t));
        if (ang < 0f) ang += MathF.PI * 2f;
        Vector3 v = n;
        float tmp = v[g]; v[g] = v.Z; v.Z = tmp;
        float s = MathF.Max(0f, MathF.Min(1f, ang / (MathF.PI * 2f)));
        float x = MathF.Min(v.X * 1.4142135f + 1f, 1.9999847f), y = MathF.Min(v.Y * 1.4142135f + 1f, 1.9999847f), z = MathF.Min(s * 4f, 3.9999847f);
        uint ix = (uint)x, iy = (uint)y, iz = (uint)z;
        uint w = (ix << 4) | (iy << 5) | (iz << 6) | face | flip;
        return new Vector4(x - ix, y - iy, z - iz, w / 255f);
    }

    static MeshSubset CloneSubset(MeshSubset t)
    {
        var c = (MeshSubset)MemberwiseCloneMethod.Invoke(t, null);
        Set(c, "_texCoordsPerMeter", ((float[])Get(t, "_texCoordsPerMeter")).Clone());
        foreach (var f in new[] { "_unknownAfterVertexData", "_unknownTrailerData", "_unknownScale", "_unknownAfterSurfaceArea" })
            if (Get(t, f) is byte[] b) Set(c, f, b.Clone());
        var decls = (GeometryDeclarationDesc[])t.GeometryDeclarationDescriptors.Clone();
        for (int i = 0; i < decls.Length; i++)
        {
            decls[i].Elements = (GeometryDeclarationDesc.Element[])decls[i].Elements.Clone();
            decls[i].Streams = (GeometryDeclarationDesc.Stream[])decls[i].Streams.Clone();
        }
        Set(c, "<GeometryDeclarationDescriptors>k__BackingField", decls);
        c.SetBones((ushort[])t.BoneIndices.Clone());
        return c;
    }

    sealed class SubsetGeometry
    {
        public float[] Pos, Nrm, Tan, Bin, Uv;
        public uint[] Idx;
        public int Vertices, Triangles;
    }

    static SubsetGeometry ReadGeometry(byte[] blob, JsonObject s)
    {
        int n = (int)s["vertices"], t = (int)s["triangles"];
        long off = (long)s["offset"];
        var g = new SubsetGeometry { Vertices = n, Triangles = t };
        float[] F(int count) { var a = new float[count]; Buffer.BlockCopy(blob, (int)off, a, 0, count * 4); off += count * 4; return a; }
        g.Pos = F(n * 3); g.Nrm = F(n * 3); g.Tan = F(n * 3); g.Bin = F(n * 3); g.Uv = F(n * 2);
        g.Idx = new uint[t * 3];
        Buffer.BlockCopy(blob, (int)off, g.Idx, 0, t * 12);
        if (off + t * 12 != (long)s["offset"] + (long)s["bytes"]) throw new InvalidDataException("geometry record size mismatch for " + (string)s["name"]);
        foreach (var i in g.Idx) if (i >= n) throw new InvalidDataException("index out of range in " + (string)s["name"]);
        return g;
    }

    // One zero-area triangle at a point: a subset that keeps its material without drawing anything (FC27 has no
    // subsets without primitives).
    static SubsetGeometry Degenerate(JsonArray at)
    {
        float x = (float)at[0], y = (float)at[1], z = (float)at[2];
        return new SubsetGeometry
        {
            Vertices = 3, Triangles = 1, Idx = new uint[] { 0, 1, 2 },
            Pos = new[] { x, y, z, x, y, z, x, y, z },
            Nrm = new[] { 0f, 1f, 0f, 0f, 1f, 0f, 0f, 1f, 0f },
            Tan = new[] { 1f, 0f, 0f, 1f, 0f, 0f, 1f, 0f, 0f },
            Bin = new[] { 0f, 0f, -1f, 0f, 0f, -1f, 0f, 0f, -1f },
            Uv = new float[6],
        };
    }

    static void WriteElement(BinaryWriter w, GeometryDeclarationDesc.Element e, SubsetGeometry g, int v, ushort part, float[] rad)
    {
        Vector3 P() => new(g.Pos[v * 3], g.Pos[v * 3 + 1], g.Pos[v * 3 + 2]);
        Vector3 N() => new(g.Nrm[v * 3], g.Nrm[v * 3 + 1], g.Nrm[v * 3 + 2]);
        Vector3 T() => new(g.Tan[v * 3], g.Tan[v * 3 + 1], g.Tan[v * 3 + 2]);
        Vector3 B() => new(g.Bin[v * 3], g.Bin[v * 3 + 1], g.Bin[v * 3 + 2]);
        void H(float x) => w.Write(BitConverter.HalfToUInt16Bits((Half)x));
        switch (e.Usage)
        {
            case VertexElementUsage.Pos:
                var p = P();
                if (e.Format == VertexElementFormat.Float3 || e.Format == VertexElementFormat.Float4) { w.Write(p.X); w.Write(p.Y); w.Write(p.Z); if (e.Format == VertexElementFormat.Float4) w.Write(1f); }
                else if (e.Format == VertexElementFormat.Half3 || e.Format == VertexElementFormat.Half4) { H(p.X); H(p.Y); H(p.Z); if (e.Format == VertexElementFormat.Half4) H(1f); }
                else throw new InvalidDataException("position format " + e.Format);
                break;
            case VertexElementUsage.BoneIndices:
                if (e.Format == VertexElementFormat.UShort2 || e.Format == VertexElementFormat.UShort2N) { w.Write(part); w.Write(part); }
                else if (e.Format == VertexElementFormat.UShort4) { w.Write(part); w.Write(part); w.Write(part); w.Write(part); }
                else if (e.Format == VertexElementFormat.UByte4 || e.Format == VertexElementFormat.UByte4N) { for (int i = 0; i < 4; i++) w.Write((byte)part); }
                else throw new InvalidDataException("bone index format " + e.Format);
                break;
            case VertexElementUsage.TexCoord0:
            case VertexElementUsage.TexCoord1:
                float u = g.Uv[v * 2], vv = g.Uv[v * 2 + 1];
                if (e.Format == VertexElementFormat.Half2) { H(u); H(vv); }
                else if (e.Format == VertexElementFormat.Float2) { w.Write(u); w.Write(vv); }
                else throw new InvalidDataException("texcoord format " + e.Format);
                break;
            case VertexElementUsage.RadiosityTexCoord:
                if (e.Format == VertexElementFormat.Float3) { w.Write(rad[0]); w.Write(rad[1]); w.Write(rad[2]); }
                else if (e.Format == VertexElementFormat.Float2) { w.Write(rad[0]); w.Write(rad[1]); }
                else if (e.Format == VertexElementFormat.Half2) { H(rad[0]); H(rad[1]); }
                else throw new InvalidDataException("radiosity format " + e.Format);
                break;
            case VertexElementUsage.TangentSpace:
                if (e.Format != VertexElementFormat.UByte4N) throw new InvalidDataException("tangent space format " + e.Format);
                var ts = PackAxisAngle(T(), B(), N());
                w.Write((byte)((int)(ts.X * 255f + 0.5f) & 0xFF)); w.Write((byte)((int)(ts.Y * 255f + 0.5f) & 0xFF));
                w.Write((byte)((int)(ts.Z * 255f + 0.5f) & 0xFF)); w.Write((byte)((int)(ts.W * 255f + 0.5f) & 0xFF));
                break;
            case VertexElementUsage.Normal: { var q = N(); H(q.X); H(q.Y); H(q.Z); H(1f); break; }
            case VertexElementUsage.Tangent: { var q = T(); H(q.X); H(q.Y); H(q.Z); H(1f); break; }
            case VertexElementUsage.Binormal: { var q = B(); H(q.X); H(q.Y); H(q.Z); H(1f); break; }
            case VertexElementUsage.Color0:
                if (e.Format != VertexElementFormat.UByte4N) throw new InvalidDataException("color format " + e.Format);
                w.Write(0xFFFFFFFFu);
                break;
            default:
                throw new InvalidDataException("unsupported vertex usage " + e.Usage);
        }
    }

    // ---------------------------------------------------------------- mesh_build
    // Rebuilds LOD 0 of a host MeshSet with one subset per prepared Morumbi subset; each subset is a clone of a
    // template subset (same declaration, flags and shader key family), the way FET's FBXImporter fills subsets.
    static void MeshBuild(JsonObject job, JsonObject row)
    {
        var data = File.ReadAllBytes((string)job["input"]);
        var meta = Convert.FromHexString((string)job["meta"]);
        var m = LoadMesh(data, (byte[])meta.Clone());
        if (m.Lods.Count != 1) throw new InvalidDataException("host mesh must have one LOD");
        var lod = m.Lods[0];
        var expectChunk = Guid.Parse((string)job["lod_chunk"]);
        if (lod.DataChunkId != expectChunk) throw new InvalidDataException($"host LOD chunk {lod.DataChunkId} != {expectChunk}");
        if (lod.InlineDataLength != 0) throw new InvalidDataException("host LOD has inline data");
        var blob = File.ReadAllBytes((string)job["geometry"]);
        var rad = job["radiosity"]!.AsArray().Select(x => (float)x).ToArray();
        var specs = job["subsets"]!.AsArray().Select(x => x!.AsObject()).ToList();
        bool composite = m.Type == MeshType.Composite;
        var newSubsets = new List<MeshSubset>();
        var geos = new List<SubsetGeometry>();
        var parts = new List<ushort[]>();
        bool wide = false;
        foreach (var s in specs)
        {
            var t = s["template"]!.AsObject();
            var tm = Template((string)t["res"], (string)t["meta"]);
            var ts = tm.Lods[0].Subsets[(int)t["subset"]];
            if (composite != (tm.Type == MeshType.Composite)) throw new InvalidDataException("template and host mesh types differ");
            var c = CloneSubset(ts);
            string name = (string)s["material_name"];
            Set(c, "<MaterialName>k__BackingField", name);
            c.MaterialNameHash = FbHash(name);
            Set(c, "<MaterialIndex>k__BackingField", (int)s["material_index"]);
            Set(c, "_subsetIndex", newSubsets.Count);
            c.ShaderExpressionInstanceKey = ulong.Parse((string)s["key"]);
            if (s["area"] is JsonValue) Set(c, "<SurfaceArea>k__BackingField", (float)(double)s["area"]);
            if (s["bbox"] is JsonArray) Set(c, "_boundingBox", MakeBox(s["bbox"]!.AsArray()));
            if (s["texel_density"] is JsonValue) ((float[])Get(c, "_texCoordsPerMeter"))[3] = (float)(double)s["texel_density"];
            var g = s["empty"] is JsonValue ev && (bool)ev
                ? new SubsetGeometry { Pos = Array.Empty<float>(), Nrm = Array.Empty<float>(), Tan = Array.Empty<float>(), Bin = Array.Empty<float>(), Uv = Array.Empty<float>(), Idx = Array.Empty<uint>() }
                : s["degenerate"] is JsonArray dg ? Degenerate(dg) : ReadGeometry(blob, s);
            ushort[] vpart = new ushort[g.Vertices];
            if (s["part_of_vertex"] is JsonArray pv) for (int i = 0; i < g.Vertices; i++) vpart[i] = (ushort)(int)pv[i];
            else Array.Fill(vpart, (ushort)(int)s["part"]);
            if (composite) c.SetBones(vpart.Distinct().OrderBy(x => x).ToArray());
            if (g.Vertices > 65535) wide = true;
            newSubsets.Add(c); geos.Add(g); parts.Add(vpart);
        }
        // Vertex data: each subset's streams one after another (FBXImporter layout), then 16-byte padding.
        var ms = new MemoryStream();
        var w = new BinaryWriter(ms);
        for (int k = 0; k < newSubsets.Count; k++)
        {
            var c = newSubsets[k]; var g = geos[k];
            c.VertexOffset = (uint)ms.Position;
            c.VertexCount = (uint)g.Vertices;
            ((float[])Get(c, "_texCoordsPerMeter"))[2] = BitConverter.Int32BitsToSingle((int)c.VertexOffset);
            var d = c.GeometryDeclarationDescriptors[0];
            for (int st = 0; st < d.StreamCount; st++)
            {
                int stride = d.Streams[st].Stride;
                var els = new List<GeometryDeclarationDesc.Element>();
                for (int e = 0; e < d.ElementCount; e++) if (d.Elements[e].StreamIndex == st && d.Elements[e].Usage != VertexElementUsage.Unknown) els.Add(d.Elements[e]);
                if (stride == 0) continue;
                var vb = new byte[stride];
                for (int v = 0; v < g.Vertices; v++)
                {
                    long start = ms.Position;
                    foreach (var e in els)
                    {
                        ms.Position = start + e.Offset;
                        WriteElement(w, e, g, v, parts[k][v], rad);
                    }
                    ms.Position = start + stride;
                    if (ms.Length < ms.Position) ms.SetLength(ms.Position);
                }
            }
            if ((int)(byte)Get(c, "_vertexStride") != Enumerable.Range(0, d.StreamCount).Sum(i => (int)d.Streams[i].Stride))
                throw new InvalidDataException("template stride differs from its streams for " + c.MaterialName);
        }
        while (ms.Position % 16 != 0) w.Write((byte)0);
        uint vertexSize = (uint)ms.Position;
        int unit = wide ? 4 : 2;
        for (int k = 0; k < newSubsets.Count; k++)
        {
            while ((ms.Position - vertexSize) % 4 != 0) w.Write((byte)0);
            var c = newSubsets[k];
            c.StartIndex = (uint)((ms.Position - vertexSize) / unit);
            Set(c, "_startIndexCopy", c.StartIndex);
            c.PrimitiveCount = (uint)geos[k].Triangles;
            foreach (var i in geos[k].Idx) { if (wide) w.Write(i); else w.Write((ushort)i); }
        }
        while (ms.Position % 4 != 0) w.Write((byte)0);
        uint indexSize = (uint)ms.Position - vertexSize;
        while (ms.Position % 16 != 0) w.Write((byte)0);
        var chunk = ms.ToArray();
        // Subset lists, categories and composite part masks.
        lod.Subsets.Clear();
        lod.Subsets.AddRange(newSubsets);
        for (int i = 0; i < lod.CategorySubsetIndices.Count; i++) lod.CategorySubsetIndices[i].Clear();
        for (int k = 0; k < specs.Count; k++)
            foreach (var cat in specs[k]["categories"]!.AsArray())
                lod.CategorySubsetIndices[(int)cat].Add((byte)k);
        if (newSubsets.Count > 255) throw new InvalidDataException("more than 255 subsets");
        if (composite)
        {
            var masks = new byte[newSubsets.Count][];
            for (int k = 0; k < masks.Length; k++)
            {
                masks[k] = new byte[24];
                foreach (var p in newSubsets[k].BoneIndices) masks[k][p / 8] |= (byte)(1 << (p % 8));
            }
            Set(lod, "<SubsetPartIndices>k__BackingField", masks);
        }
        lod.VertexDataSize = vertexSize;
        lod.IndexDataSize = indexSize;
        lod.SetIndexBufferFormatSize(unit);
        Set(m, "_boundingBox", MakeBox(job["bbox"]!.AsArray()));
        if (job["part_boxes"] is JsonObject pbs)
        {
            var pb = (AxisAlignedBox[])Get(m, "_partBoundingBoxes");
            foreach (var kv in pbs) pb[int.Parse(kv.Key)] = MakeBox(kv.Value!.AsArray());
        }
        var output = m.ToStream(game).ToArray();
        var newMeta = (byte[])m.Meta.Clone();
        // Re-read and check every subset against the input geometry (first and last vertex positions, counts).
        var check = LoadMesh(output, (byte[])newMeta.Clone());
        var cl = check.Lods[0];
        if (cl.Subsets.Count != newSubsets.Count) throw new InvalidDataException("subset count not written");
        if (!check.ToStream(game).ToArray().AsSpan().SequenceEqual(output)) throw new InvalidDataException("mesh second write differs");
        var subs = new JsonArray();
        for (int k = 0; k < cl.Subsets.Count; k++)
        {
            var s = cl.Subsets[k]; var g = geos[k];
            if (s.VertexCount != g.Vertices || s.PrimitiveCount != g.Triangles || s.MaterialName != (string)specs[k]["material_name"]
                || s.ShaderExpressionInstanceKey != ulong.Parse((string)specs[k]["key"]))
                throw new InvalidDataException("subset not written as requested: " + s.MaterialName);
            var d = s.GeometryDeclarationDescriptors[0];
            var posEl = d.Elements.Take(d.ElementCount).First(e => e.Usage == VertexElementUsage.Pos);
            if (posEl.StreamIndex != 0 || posEl.Format != VertexElementFormat.Float3) throw new InvalidDataException("position is not the first float3 stream");
            foreach (int v in g.Vertices == 0 ? Array.Empty<int>() : new[] { 0, g.Vertices - 1 })
            {
                int o = (int)s.VertexOffset + v * d.Streams[0].Stride;
                for (int a = 0; a < 3; a++)
                    if (BitConverter.ToSingle(chunk, o + a * 4) != g.Pos[v * 3 + a]) throw new InvalidDataException("vertex position mismatch in " + s.MaterialName);
            }
            subs.Add(new JsonObject { ["material"] = s.MaterialName, ["key"] = s.ShaderExpressionInstanceKey.ToString(), ["vertices"] = s.VertexCount,
                ["triangles"] = s.PrimitiveCount, ["vertex_offset"] = s.VertexOffset, ["start"] = s.StartIndex, ["material_index"] = s.MaterialIndex,
                ["flags"] = s.Flags.ToString(), ["bones"] = new JsonArray(s.BoneIndices.Select(x => (JsonNode)x).ToArray()) });
        }
        var outRes = (string)job["output_res"]; var outChunk = (string)job["output_chunk"];
        if (File.Exists(outRes) || File.Exists(outChunk)) throw new IOException("output exists");
        File.WriteAllBytes(outRes, output);
        File.WriteAllBytes(outChunk, chunk);
        row["output_res"] = outRes; row["res_sha256"] = Sha(output); row["meta"] = Hex(newMeta);
        row["output_chunk"] = outChunk; row["chunk_sha256"] = Sha(chunk); row["chunk_bytes"] = chunk.Length;
        row["vertex_size"] = vertexSize; row["index_size"] = indexSize; row["index_unit"] = unit; row["subsets"] = subs;
        row["categories"] = new JsonArray(cl.CategorySubsetIndices.Select(c => (JsonNode)new JsonArray(c.Select(x => (JsonNode)x).ToArray())).ToArray());
    }

    // ---------------------------------------------------------------- mesh_subset_counts
    // Keeps a mesh's data and only changes subset counts / LOD vertex positions (used to empty or move geometry).
    static void MeshEdit(JsonObject job, JsonObject row)
    {
        var data = File.ReadAllBytes((string)job["input"]);
        var meta = Convert.FromHexString((string)job["meta"]);
        var m = LoadMesh(data, (byte[])meta.Clone());
        var lod = m.Lods[0];
        if (job["empty_subsets"] is JsonArray empty)
            foreach (var x in empty)
            {
                var s = lod.Subsets[(int)x];
                s.VertexCount = 0; s.PrimitiveCount = 0;
            }
        if (job["export_inline"] is JsonValue exi)
        {
            var path0 = (string)exi;
            if (File.Exists(path0)) throw new IOException("output exists: " + path0);
            File.WriteAllBytes(path0, lod.GetInlineDataSpan().ToArray());
            row["inline_bytes"] = lod.InlineDataLength;
            return;
        }
        if (job["inline_data"] is JsonValue inl)
        {
            var bytes = File.ReadAllBytes((string)inl);
            if (bytes.Length != lod.InlineDataLength) throw new InvalidDataException("inline data size changes");
            lod.SetInlineData(bytes);
        }
        var output = m.ToStream(game).ToArray();
        var newMeta = (byte[])m.Meta.Clone();
        var check = LoadMesh(output, (byte[])newMeta.Clone());
        if (!check.ToStream(game).ToArray().AsSpan().SequenceEqual(output)) throw new InvalidDataException("mesh second write differs");
        var outRes = (string)job["output_res"];
        if (File.Exists(outRes)) throw new IOException("output exists");
        File.WriteAllBytes(outRes, output);
        row["output_res"] = outRes; row["res_sha256"] = Sha(output); row["meta"] = Hex(newMeta);
        row["subsets"] = new JsonArray(check.Lods[0].Subsets.Select(s => (JsonNode)new JsonObject { ["material"] = s.MaterialName, ["vertices"] = s.VertexCount, ["triangles"] = s.PrimitiveCount }).ToArray());
    }

    // ---------------------------------------------------------------- texture_build
    // A new texture from a prepared BC mip chain, header derived from a template texture the way FET's
    // TextureImporter.AddDDSAsync does (CalculateMipmapData, name hash, chunk compressed with the texture
    // so the header's compressed mip offsets are filled).
    static void TextureBuild(JsonObject job, JsonObject row)
    {
        var header = Texture.LoadHeader(game, new MemoryStream(File.ReadAllBytes((string)job["template"])));
        var tex = (Texture)RuntimeHelpers.GetUninitializedObject(typeof(Texture));
        Set(tex, "<Header>k__BackingField", header);
        if (header.Type != TextureType.TT_2d) throw new InvalidDataException("template is not a 2D texture");
        string fmt = (string)job["format"];
        bool rawFormat = fmt == "RAW";
        // RenderFormat names: BC1_SRGB / BC1A_SRGB (1-bit alpha) / BC3_SRGB, or _UNORM when the template is linear.
        string space = header.PixelFormat.EndsWith("_SRGB") ? "_SRGB" : "_UNORM";
        bool alpha = job["alpha"] is JsonValue av && (bool)av;
        string pf = rawFormat ? header.PixelFormat : (fmt == "BC1" ? (alpha ? "BC1A" : "BC1") : fmt == "BC3" ? "BC3" : throw new InvalidDataException("format " + fmt)) + space;
        var renderFormat = TypeRegistry.GetType("RenderFormat").ClrType;
        tex.PixelFormatInt32 = (int)Enum.Parse(renderFormat, "RenderFormat_" + pf);
        var chain = File.ReadAllBytes((string)job["data"]);
        if (Sha(chain) != (string)job["sha256"]) throw new InvalidDataException("mip chain hash mismatch");
        int mips = (int)job["mips"];
        tex.Width = (ushort)(int)job["width"]; tex.Height = (ushort)(int)job["height"];
        tex.Depth = 1; tex.DepthWithPadding = 1;
        tex.MipmapBaseIndex = (byte)(mips > tex.MipmapBaseIndex ? tex.MipmapBaseIndex : 0);
        string name = (string)job["name"];
        tex.ResourceNameHash = Sdk.Hash.Djb2Hash.HashString64(name);
        if (rawFormat) tex.CalculateMipmapData((byte)mips, (int)job["bits_per_pixel"], false, (uint)chain.Length, game);
        else tex.CalculateMipmapData((byte)mips, fmt == "BC1" ? 8 : 16, true, (uint)chain.Length, game);
        // CalculateMipmapData counts pixel rows, which is short for BC mips whose height is not a multiple of 4;
        // the stored sizes are the real BC sizes (ceil(w/4) * ceil(h/4) blocks), with the dependent fields recomputed.
        var expected = job["mip_sizes"]!.AsArray().Select(x => (uint)x).ToArray();
        int fixedMips = 0;
        for (int i = 0; i < mips; i++) if (tex.MipmapSizes[i] != expected[i]) { tex.MipmapSizes[i] = expected[i]; fixedMips++; }
        uint total = 0;
        for (int i = 0; i < mips; i++) total += tex.MipmapSizes[i];
        if (total != chain.Length) throw new InvalidDataException($"mip sizes {total} != data {chain.Length}");
        if (fixedMips > 0)
        {
            tex.MipmapChainSize = total;
            uint lo = 0;
            for (int i = 0; i < tex.MipmapBaseIndex; i++) lo += tex.MipmapSizes[i];
            if ((tex.Flags & TextureFlags.OnDemandLoaded) != 0) { tex.LogicalOffset = 0; tex.LogicalSize = 0; }
            else if (mips > 1) { tex.LogicalOffset = lo; tex.LogicalSize = total - lo; }
            else { tex.LogicalOffset = 0; tex.LogicalSize = total; }
            var info = (ulong)typeof(TextureHeader).GetMethod("ComputeMipStreamingInfo", BindingFlags.NonPublic | BindingFlags.Instance)!.Invoke(header, new object[] { game.FrostbiteVersion });
            typeof(TextureHeader).GetProperty("MipStreamingInfo")!.SetValue(header, info);
        }
        row["mip_sizes_fixed"] = fixedMips;
        tex.StreamingChunkId = Guid.Parse((string)job["chunk"]);
        // The chunk is stored uncompressed (CAS codec 0, 64 KiB blocks, as the project writer frames raw payloads);
        // the compressed mip offsets are what Sdk.Compression.UpdateTextureMipOffsets computes for that framing.
        tex.CompressedChunkOffsets[0] = 0; tex.CompressedChunkOffsets[1] = 0;
        long read = 0, written = 0;
        while (read < chain.Length)
        {
            int n = (int)Math.Min(65536, chain.Length - read);
            read += n; written += 8 + n;
            if (tex.MipmapCount > 1)
            {
                if (read == tex.MipmapSizes[0]) { tex.CompressedChunkOffsets[0] = tex.CompressedChunkOffsets[1] = (uint)written; }
                else if (read == tex.MipmapSizes[0] + tex.MipmapSizes[1]) tex.CompressedChunkOffsets[1] = (uint)written;
            }
        }
        var res = tex.ToStream(game).ToArray();
        var check = Texture.LoadHeader(game, new MemoryStream(res));
        if (check.Width != tex.Width || check.Height != tex.Height || check.MipmapCount != mips || check.StreamingChunkId != tex.StreamingChunkId
            || check.PixelFormat != pf || check.ResourceNameHash != tex.ResourceNameHash) throw new InvalidDataException("texture header not written");
        if (!check.ToStream(game).ToArray().AsSpan().SequenceEqual(res)) throw new InvalidDataException("texture header does not round trip");
        if (check.CompressedChunkOffsets[0] != tex.CompressedChunkOffsets[0] || check.CompressedChunkOffsets[1] != tex.CompressedChunkOffsets[1]) throw new InvalidDataException("mip offsets not written");
        string outRes = (string)job["output_res"], outChunk = (string)job["output_chunk"];
        if (File.Exists(outRes) || File.Exists(outChunk)) throw new IOException("output exists");
        File.WriteAllBytes(outRes, res);
        File.WriteAllBytes(outChunk, chain);
        row["output_res"] = outRes; row["res_sha256"] = Sha(res); row["output_chunk"] = outChunk; row["chunk_sha256"] = Sha(chain);
        row["chunk_bytes"] = chain.Length; row["original_size"] = chain.Length; row["pixel_format"] = pf;
        row["logical_offset"] = tex.LogicalOffset; row["logical_size"] = tex.LogicalSize; row["mip_base"] = tex.MipmapBaseIndex;
        row["compressed_offsets"] = new JsonArray(tex.CompressedChunkOffsets[0], tex.CompressedChunkOffsets[1]);
        row["codec"] = "None"; row["name_hash"] = tex.ResourceNameHash.ToString();
    }

    // ---------------------------------------------------------------- sbd_extend
    // Appends entries to a shader block depot: each new key gets a private copy of a template entry's block with
    // some texture references remapped (FET PrepareExpressionShaderBundle + RemapTextureReferences, per entry).
    static void SbdExtend(JsonObject job, JsonObject row)
    {
        var data = File.ReadAllBytes((string)job["input"]);
        var depot = LoadSbd(data, Convert.FromHexString((string)job["meta"]));
        int before = depot.Entries.Count;
        var added = new JsonArray();
        foreach (var node in job["entries"]!.AsArray())
        {
            var e = node!.AsObject();
            ulong tk = ulong.Parse((string)e["template_key"]), nk = ulong.Parse((string)e["new_key"]);
            if (!depot.TryGetEntry(tk, out var te)) throw new InvalidDataException($"template key {tk} not in depot");
            if (depot.TryGetEntry(nk, out _)) throw new InvalidDataException($"new key {nk} already in depot");
            var single = ShaderBlockDepotResource.CreateEmpty().AppendEntriesFrom(depot, (IReadOnlyDictionary<ulong, ulong>)new Dictionary<ulong, ulong> { [tk] = nk });
            var inst = new Dictionary<Guid, Guid>(); var part = new Dictionary<Guid, Guid>();
            foreach (var r in e["remap"]!.AsArray())
            {
                var o = r!.AsObject();
                inst[Guid.Parse((string)o["old_instance"])] = Guid.Parse((string)o["new_instance"]);
                part[Guid.Parse((string)o["old_partition"])] = Guid.Parse((string)o["new_partition"]);
            }
            int found = single.Blocks[0].TextureParameters.Count(t => inst.ContainsKey(t.InstanceGuid) && part.ContainsKey(t.PartitionGuid));
            if (found != inst.Count) throw new InvalidDataException($"template block of {tk} lacks a texture to remap ({found}/{inst.Count})");
            single.RemapTextureReferences(inst, part);
            depot = depot.AppendEntriesFrom(single, (IReadOnlyCollection<ulong>)new[] { nk });
            depot.TryGetEntry(nk, out var ne);
            added.Add(new JsonObject { ["key"] = nk.ToString(), ["textures"] = new JsonArray(ne.Block.TextureParameters.Select(t => (JsonNode)$"{t.PartitionGuid}/{t.InstanceGuid}").ToArray()) });
        }
        var output = depot.ToArray();
        var meta = (byte[])depot.Meta.Clone();
        var check = LoadSbd(output, (byte[])meta.Clone());
        if (check.Entries.Count != before + added.Count) throw new InvalidDataException("entry count");
        // The original entries keep their blocks byte for byte.
        var orig = LoadSbd(data, Convert.FromHexString((string)job["meta"]));
        foreach (var oe in orig.Entries)
        {
            check.TryGetEntry(oe.KeyHash, out var ce);
            if (ce == null || !ce.Block.HasSameContent(oe.Block)) throw new InvalidDataException("existing entry changed: " + oe.KeyHash);
        }
        var path = (string)job["output"];
        if (File.Exists(path)) throw new IOException("output exists: " + path);
        File.WriteAllBytes(path, output);
        row["output"] = path; row["sha256"] = Sha(output); row["meta"] = Hex(meta); row["entries_before"] = before; row["entries_after"] = check.Entries.Count; row["added"] = added;
    }

    static ShaderBlockDepotResource LoadSbd(byte[] data, byte[] meta) => new ShaderBlockDepotResource(new ArraySegment<byte>(data), meta);
}
