// Desfazer / refazer. Cada comando guarda o "antes" e o "depois" e sabe aplicar os dois.
export class Historico extends EventTarget {
  constructor(limite = 300) {
    super();
    this.limite = limite;
    this.pilha = [];
    this.pos = 0;
  }

  limpar() { this.pilha = []; this.pos = 0; this.mudou(); }

  executar(cmd) {
    cmd.refazer();
    this.pilha.length = this.pos;
    // comandos contínuos (ex.: arrastar um valor) se fundem com o anterior de mesma chave
    const ult = this.pilha[this.pilha.length - 1];
    if (ult && cmd.fundir && ult.fundir === cmd.fundir && Date.now() - ult.quando < 1200) {
      ult.refazer = cmd.refazer;
      ult.quando = Date.now();
    } else {
      cmd.quando = Date.now();
      this.pilha.push(cmd);
      if (this.pilha.length > this.limite) this.pilha.shift();
    }
    this.pos = this.pilha.length;
    this.mudou();
  }

  desfazer() {
    if (!this.pos) return null;
    const c = this.pilha[--this.pos];
    c.desfazer();
    this.mudou();
    return c;
  }

  refazer() {
    if (this.pos >= this.pilha.length) return null;
    const c = this.pilha[this.pos++];
    c.refazer();
    this.mudou();
    return c;
  }

  get podeDesfazer() { return this.pos > 0; }
  get podeRefazer() { return this.pos < this.pilha.length; }
  get proximoDesfazer() { return this.pos ? this.pilha[this.pos - 1].nome : ''; }
  get proximoRefazer() { return this.pos < this.pilha.length ? this.pilha[this.pos].nome : ''; }

  mudou() { this.dispatchEvent(new Event('mudou')); }
}
