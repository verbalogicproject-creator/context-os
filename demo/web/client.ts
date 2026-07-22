export async function fetchItems(): Promise<string[]> {
  const r = await fetch("/items");
  return r.json();
}
export async function addItem(name: string): Promise<void> {
  await fetch("/items/add", { method: "POST", body: name });
}
