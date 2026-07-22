import { fetchItems, addItem } from "./client";
export async function render() {
  const items = await fetchItems();
  return items.map((i) => `<li>${i}</li>`).join("");
}
export { addItem };
