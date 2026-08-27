const token = sessionStorage.getItem("token");
if (!token) location.href = "/login.html";
const headers = {"Authorization": `Bearer ${token}`, "Content-Type": "application/json"};
const message = document.querySelector("#message");
const templatePicker = document.querySelector("#template-picker");
const templateSelect = document.querySelector("#template-select");

async function request(path, options = {}) {
  const response = await fetch(path, {...options, headers: {...headers, ...(options.headers || {})}});
  if (response.status === 401) { sessionStorage.removeItem("token"); location.href = "/login.html"; }
  if (!response.ok) throw new Error((await response.json()).detail || "Ошибка запроса");
  return response.status === 204 ? null : response.json();
}

async function loadVMs() {
  try {
    const vms = await request("/api/vms");
    document.querySelector("#vms").innerHTML = vms.map(vm => `
      <tr><td>${vm.vmid}</td><td>${vm.name}</td><td>${vm.template_label || (vm.template_vmid ? `VMID ${vm.template_vmid}` : "—")}</td><td>${vm.status}</td>
      <td><a class="button" href="/console.html?vmid=${vm.vmid}">Консоль</a>
      <button data-action="start" data-vmid="${vm.vmid}">Старт</button>
      <button data-action="stop" data-vmid="${vm.vmid}">Стоп</button>
      <button data-action="delete" data-vmid="${vm.vmid}" class="danger">Удалить</button></td></tr>
    `).join("");
  } catch (error) { message.textContent = error.message; message.className = "error"; }
}

async function loadTemplates() {
  const templates = await request("/api/templates");
  templateSelect.innerHTML = templates.map(template =>
    `<option value="${template.vmid}">${template.label}</option>`
  ).join("");
  templatePicker.hidden = templates.length < 2;
}

document.querySelector("#get-vm").addEventListener("click", async () => {
  try {
    await request("/api/vms", {
      method: "POST",
      body: JSON.stringify({template_vmid: Number(templateSelect.value)})
    });
    message.textContent = "ВМ создана";
    await loadVMs();
  }
  catch (error) { message.textContent = error.message; message.className = "error"; }
});
document.querySelector("#vms").addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const vmid = button.dataset.vmid;
  try {
    await request(`/api/vms/${vmid}/${button.dataset.action}`, {method: "POST"});
    if (button.dataset.action === "delete") message.textContent = "ВМ удалена";
    await loadVMs();
  } catch (error) { message.textContent = error.message; message.className = "error"; }
});
document.querySelector("#logout").addEventListener("click", () => { sessionStorage.removeItem("token"); location.href = "/login.html"; });
Promise.all([loadTemplates(), loadVMs()]).catch(error => {
  message.textContent = error.message;
  message.className = "error";
});
