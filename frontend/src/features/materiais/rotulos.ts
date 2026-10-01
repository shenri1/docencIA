import type { Material } from "../../api/tipos";

export const ROTULO_TIPO: Record<Material["tipo"], string> = {
  slide: "Slide",
  pdf: "PDF",
  livro: "Livro",
};

export const ROTULO_FORMATO: Record<Material["formato"], string> = {
  pdf: "PDF",
  pptx: "PPTX",
  docx: "DOCX",
  txt: "TXT",
};

export const ROTULO_ORIGEM: Record<Material["origem_texto"], string> = {
  nativo: "texto nativo",
  ocr: "reconhecido por OCR",
  misto: "texto nativo e OCR",
};
