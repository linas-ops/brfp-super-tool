// Tipos que o SDK do FIFA Editor Tool 2.2.0 (compilado para .NET 11) usa e que o .NET 8 não tem.
// O PrepararSdk redireciona para cá as referências a eles; o resto do SDK roda no .NET 8 sem mudança.
using System.Runtime.CompilerServices;

namespace System.Threading
{
    // System.Threading.Lock (.NET 9+): o mesmo comportamento sobre o Monitor.
    public sealed class Lock
    {
        public Lock() { }
        public void Enter() => Monitor.Enter(this);
        public bool TryEnter() => Monitor.TryEnter(this);
        public bool TryEnter(int millisecondsTimeout) => Monitor.TryEnter(this, millisecondsTimeout);
        public void Exit() => Monitor.Exit(this);
        public bool IsHeldByCurrentThread => Monitor.IsEntered(this);
        public Scope EnterScope() { Monitor.Enter(this); return new Scope(this); }

        public ref struct Scope
        {
            Lock owner;
            internal Scope(Lock l) { owner = l; }
            public void Dispose()
            {
                var l = owner;
                if (l != null) { owner = null; Monitor.Exit(l); }
            }
        }
    }
}

namespace System.Runtime.CompilerServices
{
    // Buffers que o compilador do .NET 10+ usa para argumentos params ReadOnlySpan (o .NET 8 já entende [InlineArray]).
    [InlineArray(2)] public struct InlineArray2<T> { private T t; }
    [InlineArray(3)] public struct InlineArray3<T> { private T t; }
    [InlineArray(4)] public struct InlineArray4<T> { private T t; }
    [InlineArray(5)] public struct InlineArray5<T> { private T t; }
    [InlineArray(6)] public struct InlineArray6<T> { private T t; }
    [InlineArray(7)] public struct InlineArray7<T> { private T t; }
    [InlineArray(8)] public struct InlineArray8<T> { private T t; }

    // Atributos só de compilação (.NET 9+).
    [AttributeUsage(AttributeTargets.Parameter)] public sealed class ParamCollectionAttribute : Attribute { }

    [AttributeUsage(AttributeTargets.Method | AttributeTargets.Constructor | AttributeTargets.Property)]
    public sealed class OverloadResolutionPriorityAttribute : Attribute
    {
        public OverloadResolutionPriorityAttribute(int priority) { Priority = priority; }
        public int Priority { get; }
    }
}

namespace Compat
{
    using System;

    using System.Threading.Tasks;

    // Uma classe <Tipo>Compat por tipo do .NET; o PrepararSdk casa nome, retorno e parâmetros.
    public static class StringCompat
    {
        // string.LastIndexOf(char, StringComparison) (.NET 9+).
        public static int LastIndexOf(string value, char c, StringComparison comparison) =>
            value.LastIndexOf(c.ToString(), comparison);

        // Sobrecargas params ReadOnlySpan (.NET 9+).
        public static string Format(string format, ReadOnlySpan<object> args) => string.Format(format, args.ToArray());
        public static string Join(string separator, ReadOnlySpan<object> values) => string.Join(separator, values.ToArray());
    }

    public static class PathCompat
    {
        public static string Combine(ReadOnlySpan<string> paths) => System.IO.Path.Combine(paths.ToArray());
    }

    public static class TimeSpanCompat
    {
        public static TimeSpan FromSeconds(long seconds) => TimeSpan.FromSeconds((double)seconds);
        public static TimeSpan FromMinutes(long minutes) => TimeSpan.FromMinutes((double)minutes);
    }

    public static class TaskCompat
    {
        public static void WaitAll(ReadOnlySpan<Task> tasks) => Task.WaitAll(tasks.ToArray());
    }
}
