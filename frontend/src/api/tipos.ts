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
