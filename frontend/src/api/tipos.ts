import type { components } from "./schema";

type Schemas = components["schemas"];

export type Docente = Schemas["DocenteResposta"];
export type Sessao = Schemas["SessaoResposta"];
export type SessaoCriar = Schemas["SessaoCriar"];
export type MarcoSessao = Schemas["MarcoSessaoResposta"];
export type MarcoBanco = Schemas["MarcoBancoResposta"];
export type Marco = MarcoSessao["marco"];
export type Material = Schemas["MaterialResposta"];
export type Indice = Schemas["IndiceResposta"];
export type TipoMaterial = Material["tipo"];
export type ResumoBanco = Schemas["ResumoBancoResposta"];
export type Banco = Schemas["BancoResposta"];
export type Prompt = Schemas["PromptResposta"];
export type PromptCriar = Schemas["PromptCriar"];
export type RegistroAuditoria = Schemas["RegistroAuditoriaResposta"];
export type TipoEventoAuditoria = Schemas["TipoEventoAuditoria"];
export type Questao = Schemas["QuestaoResposta"];
export type RelatorioImpacto = Schemas["RelatorioImpactoResposta"];
export type PropostaSubstituicao = Schemas["PropostaSubstituicaoResposta"];
export type ResumoAuditoria = Schemas["ResumoAuditoriaResposta"];
export type Achado = Schemas["AchadoResposta"];
export type RiscoAuditoria = Schemas["RiscoAuditoria"];
export type Prova = Schemas["ProvaResposta"];
export type ProvasMontadas = Schemas["ProvasMontadasResposta"];
export type Gabarito = Schemas["GabaritoResposta"];
export type ItemGabarito = Schemas["ItemGabaritoResposta"];
export type Exportacao = Schemas["ExportacaoResposta"];

export type Orientacao = Schemas["OrientacaoResposta"];
export type DirecaoVariacao = Schemas["DirecaoVariacao"];
