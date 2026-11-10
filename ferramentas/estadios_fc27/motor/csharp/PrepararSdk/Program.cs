// Prepara as DLLs do SDK do FIFA Editor Tool (compiladas para .NET 10/11) para rodar no .NET 8.
// PrepararSdk <pasta do Microsoft.NETCore.App 8.x> <Compat.dll> <pasta de saída> <entrada.dll> [<entrada.dll> ...]
// Nada é baixado e nada é distribuído: lê as DLLs do FET do próprio usuário e grava cópias locais em que
//  - as referências a assemblies do .NET passam para a versão 8.0.0.0;
//  - um tipo que o .NET 8 não tem no assembly citado vai para o System.Private.CoreLib (onde o .NET 8 o define)
//    ou para o Compat (System.Threading.Lock);
//  - um método que o .NET 8 não tem é trocado pelo equivalente estático do Compat (string.LastIndexOf(char, StringComparison));
//  - atributos de segurança de tipos que o .NET 8 não resolve saem.
// Tipos e métodos sem equivalente que não estão nessas regras (ex.: InlineArrayN, OverloadResolutionPriorityAttribute,
// usados só em código que as ferramentas não executam) ficam como estão e são listados em "sem_equivalente".
// O IL não muda em mais nada. Saída: uma linha JSON por DLL com o que foi trocado.
// As entradas são processadas na ordem dada: o Sdk.dll antes do FC27SDK.dll, que o cita.
using System.Text.Json;
using Mono.Cecil;
using Mono.Cecil.Cil;

static class Program
{
    static int Main(string[] args)
    {
        if (args.Length < 4) { Console.Error.WriteLine("uso: PrepararSdk <net8 dir> <Compat.dll> <saida> <entrada.dll>..."); return 2; }
        var net8 = Path.GetFullPath(args[0]);
        var compatPath = Path.GetFullPath(args[1]);
        var outDir = Path.GetFullPath(args[2]);
        Directory.CreateDirectory(outDir);
        var inputs = args.Skip(3).Select(Path.GetFullPath).ToList();
        var framework = new HashSet<string>(Directory.GetFiles(net8, "*.dll").Select(f => Path.GetFileNameWithoutExtension(f)), StringComparer.OrdinalIgnoreCase);
        var compat = ModuleDefinition.ReadModule(compatPath);
        var compatTypes = compat.Types.ToDictionary(t => t.FullName);
        var coreLib = ModuleDefinition.ReadModule(Path.Combine(net8, "System.Private.CoreLib.dll"));
        var coreTypes = new HashSet<string>(coreLib.Types.Select(t => t.FullName));
        int failed = 0;
        foreach (var input in inputs)
        {
            var log = new Dictionary<string, object> { ["dll"] = Path.GetFileName(input) };
            try { Retarget(input, outDir, net8, framework, compat, compatTypes, coreTypes, log); log["ok"] = true; }
            catch (Exception ex) { failed++; log["ok"] = false; log["erro"] = ex.ToString(); }
            Console.WriteLine(JsonSerializer.Serialize(log));
        }
        return failed == 0 ? 0 : 1;
    }

    static void Retarget(string input, string outDir, string net8, HashSet<string> framework, ModuleDefinition compat,
                         Dictionary<string, TypeDefinition> compatTypes, HashSet<string> coreTypes, Dictionary<string, object> log)
    {
        var resolver = new DefaultAssemblyResolver();
        foreach (var d in resolver.GetSearchDirectories()) resolver.RemoveSearchDirectory(d);
        resolver.AddSearchDirectory(net8);
        resolver.AddSearchDirectory(outDir);
        resolver.AddSearchDirectory(Path.GetDirectoryName(input));
        resolver.AddSearchDirectory(Path.GetDirectoryName(compat.FileName));
        var module = ModuleDefinition.ReadModule(input, new ReaderParameters { AssemblyResolver = resolver, ReadingMode = ReadingMode.Immediate });
        var versions = new List<string>();
        foreach (var r in module.AssemblyReferences)
            if (framework.Contains(r.Name) && r.Version.Major > 8)
            {
                versions.Add($"{r.Name}: {r.Version} -> 8.0.0.0");
                r.Version = new Version(8, 0, 0, 0);
            }
        log["versoes"] = versions;
        AssemblyNameReference coreRef = null, compatRef = null;
        AssemblyNameReference CoreRef()
        {
            coreRef ??= module.AssemblyReferences.FirstOrDefault(a => a.Name == "System.Private.CoreLib");
            if (coreRef == null)
            {
                coreRef = new AssemblyNameReference("System.Private.CoreLib", new Version(8, 0, 0, 0)) { PublicKeyToken = new byte[] { 0x7c, 0xec, 0x85, 0xd7, 0xbe, 0xa7, 0x79, 0x8e } };
                module.AssemblyReferences.Add(coreRef);
            }
            return coreRef;
        }
        AssemblyNameReference CompatRef()
        {
            compatRef ??= module.AssemblyReferences.FirstOrDefault(a => a.Name == "Compat");
            if (compatRef == null)
            {
                compatRef = new AssemblyNameReference("Compat", compat.Assembly.Name.Version);
                module.AssemblyReferences.Add(compatRef);
            }
            return compatRef;
        }
        // Tipos: o que não resolve no .NET 8 pelo assembly citado.
        var types = new List<string>();
        var missing = new List<string>();
        foreach (var t in module.GetTypeReferences().ToList())
        {
            if (t.Scope is not AssemblyNameReference scope || !framework.Contains(scope.Name)) continue;
            if (Resolves(t)) continue;
            if (coreTypes.Contains(t.FullName)) { t.Scope = CoreRef(); types.Add($"{t.FullName}: {scope.Name} -> System.Private.CoreLib"); }
            else if (compatTypes.ContainsKey(t.FullName)) { t.Scope = CompatRef(); types.Add($"{t.FullName}: {scope.Name} -> Compat"); }
            else { missing.Add($"{t.FullName} ({scope.Name})"); continue; }
            if (!Resolves(t)) throw new InvalidDataException($"tipo continua sem resolver: {t.FullName}");
        }
        log["tipos"] = types;
        // Métodos que o .NET 8 não tem: equivalente estático no Compat (this como primeiro parâmetro).
        var swap = new Dictionary<MemberReference, MethodReference>();
        var methods = new List<string>();
        foreach (var m in module.GetMemberReferences().OfType<MethodReference>().ToList())
        {
            var dt = m.DeclaringType.GetElementType();
            if (dt.Scope is not AssemblyNameReference scope || !(framework.Contains(scope.Name) || scope.Name == "System.Private.CoreLib")) continue;
            if (m.DeclaringType.Resolve() == null) continue;  // tipos de fora do .NET já foram tratados acima
            MethodDefinition def;
            try { def = m.Resolve(); } catch (AssemblyResolutionException) { def = null; }
            if (def != null) continue;
            // Equivalente: método estático de Compat.<Tipo>Compat com o mesmo nome, retorno e parâmetros
            // (num método de instância, o objeto vem antes como primeiro parâmetro). Métodos genéricos ficam de fora.
            int self = m.HasThis ? 1 : 0;
            var repl = m.HasGenericParameters || m is GenericInstanceMethod ? null : compat.Types.Where(x => x.Name == dt.Name + "Compat")
                .SelectMany(x => x.Methods).FirstOrDefault(c => c.IsStatic && c.Name == m.Name
                && c.Parameters.Count == m.Parameters.Count + self && (self == 0 || c.Parameters[0].ParameterType.FullName == dt.FullName)
                && c.Parameters.Skip(self).Select(p => p.ParameterType.FullName).SequenceEqual(m.Parameters.Select(p => p.ParameterType.FullName))
                && c.ReturnType.FullName == m.ReturnType.FullName);
            if (repl == null) { missing.Add(m.FullName); continue; }
            CompatRef();
            swap[m] = module.ImportReference(repl);
            methods.Add($"{m.FullName} -> {repl.FullName}");
        }
        int calls = 0;
        if (swap.Count > 0)
            foreach (var t in module.GetTypes())
                foreach (var md in t.Methods.Where(x => x.HasBody))
                    foreach (var ins in md.Body.Instructions)
                        if (ins.Operand is MethodReference mr && swap.TryGetValue(mr, out var to))
                        {
                            if (ins.OpCode != OpCodes.Call && ins.OpCode != OpCodes.Callvirt) throw new InvalidDataException("uso não suportado de " + mr.FullName + " em " + md.FullName);
                            ins.OpCode = OpCodes.Call;
                            ins.Operand = to;
                            calls++;
                        }
        log["metodos"] = methods;
        log["chamadas_trocadas"] = calls;
        log["sem_equivalente"] = missing;
        // Atributos de segurança declarativa cujo tipo o .NET 8 não resolve.
        int sec = 0;
        foreach (var holder in new ISecurityDeclarationProvider[] { module.Assembly }.Concat(module.GetTypes()).Concat(module.GetTypes().SelectMany(t => t.Methods)))
        {
            if (!holder.HasSecurityDeclarations) continue;
            foreach (var d in holder.SecurityDeclarations.ToList())
                if (d.SecurityAttributes.Any(a => a.AttributeType.Resolve() == null)) { holder.SecurityDeclarations.Remove(d); sec++; }
        }
        log["seguranca_removida"] = sec;
        var dest = Path.Combine(outDir, Path.GetFileName(input));
        if (File.Exists(dest)) throw new IOException("saída já existe: " + dest);
        module.Write(dest);
        // Releitura: tudo o que o módulo cita do .NET resolve no .NET 8.
        var check = ModuleDefinition.ReadModule(dest, new ReaderParameters { AssemblyResolver = resolver });
        var known = new HashSet<string>(missing);
        foreach (var t in check.GetTypeReferences())
            if (t.Scope is AssemblyNameReference s && (framework.Contains(s.Name) || s.Name == "System.Private.CoreLib" || s.Name == "Compat") && !Resolves(t)
                && !known.Contains($"{t.FullName} ({s.Name})"))
                throw new InvalidDataException("após gravar, tipo não resolve: " + t.FullName);
    }

    static bool Resolves(TypeReference t)
    {
        try { return t.Resolve() != null; } catch (AssemblyResolutionException) { return false; }
    }
}
