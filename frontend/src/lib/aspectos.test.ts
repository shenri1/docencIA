import { agruparPorItem, letraDoItem } from "./aspectos";

describe("agruparPorItem", () => {
  it("sem item é um grupo só", () => {
    const aspectos = [{ ordem: 1 }, { ordem: 2, item: null }];
    expect(agruparPorItem(aspectos)).toEqual([{ item: null, aspectos }]);
  });

  it("agrupa em ordem pelos itens", () => {
    const grupos = agruparPorItem([
      { ordem: 1, item: 1 },
      { ordem: 2, item: 1 },
      { ordem: 3, item: 2 },
    ]);
    expect(grupos.map((g) => [g.item, g.aspectos.length])).toEqual([
      [1, 2],
      [2, 1],
    ]);
  });

  it("letra do item", () => {
    expect([1, 2, 3].map(letraDoItem)).toEqual(["a", "b", "c"]);
  });
});
