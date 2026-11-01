import type { ReactNode } from "react";
import { Alerta } from "../../components/Alerta";
import { CascaPublica } from "./CascaPublica";

/**
 * Descreve só o que o código faz. Controlador e contato não são
 * inventados — ficam a definir pela instituição que hospeda o sistema.
 */
export function Privacidade() {
  return (
    <CascaPublica>
      <article className="flex max-w-3xl flex-col gap-6">
        <h1 className="font-serifa text-titulo">Política de privacidade</h1>
        <p className="font-serifa text-corpo-lg">
          Esta página descreve o que o docencIA faz com os seus dados, do jeito que o sistema
          funciona hoje.
        </p>
        <Alerta variante="aviso" titulo="Controlador e contato">
          O controlador dos dados e o canal de contato estão a definir pela instituição que
          hospeda o sistema.
        </Alerta>

        <Secao titulo="Dados da conta">
          Nome, credencial institucional e perfil. A senha é guardada só como hash bcrypt,
          nunca em texto.
        </Secao>
        <Secao titulo="Dados de trabalho">
          Os materiais que você envia, o texto extraído deles e o índice, as questões, as
          provas e os arquivos exportados ficam ligados à conta que os criou.
        </Secao>
        <Secao titulo="Acesso">
          O token de acesso fica no armazenamento da aba do navegador (sessionStorage) e some
          quando a aba é fechada.
        </Secao>
        <Secao titulo="Log de auditoria">
          Os eventos críticos (geração, exclusão, congelamento, montagem, exportação, falhas de
          acesso) são registrados com o autor como pseudônimo HMAC, nunca com nome ou
          credencial, e o registro guarda só identificadores e contagens. O log é
          mantido por no mínimo 12 meses, e o sistema não apaga registros dele.
        </Secao>
        <Secao titulo="Modelos de linguagem">
          Para gerar, revisar e auditar questões, o texto dos materiais é enviado aos modelos de
          linguagem configurados pela instituição que hospeda o sistema.
        </Secao>
        <Secao titulo="Exclusão">
          Nesta versão não há exclusão de conta pela interface.
        </Secao>
      </article>
    </CascaPublica>
  );
}

function Secao({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-serifa text-subtitulo">{titulo}</h2>
      <p className="font-grotesca">{children}</p>
    </section>
  );
}
