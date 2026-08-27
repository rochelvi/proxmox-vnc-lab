const token = sessionStorage.getItem("token");
if (!token) location.href = "/login.html";
const headers = {"Authorization": `Bearer ${token}`, "Content-Type": "application/json"};
const message = document.querySelector("#message");
const templatePicker = document.querySelector("#template-picker");
const templateSelect = document.querySelector("#template-select");
const getVmButton = document.querySelector("#get-vm");
const loadingOverlay = document.querySelector("#vm-loading-overlay");
const passwordButton = document.querySelector("#change-password");
const passwordOverlay = document.querySelector("#password-overlay");
const passwordForm = document.querySelector("#password-form");
const passwordMessage = document.querySelector("#password-message");

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

getVmButton.addEventListener("click", async () => {
  message.textContent = "";
  message.className = "";
  getVmButton.disabled = true;
  templateSelect.disabled = true;
  if (loadingOverlay) loadingOverlay.hidden = false;

  try {
    await request("/api/vms", {
      method: "POST",
      body: JSON.stringify({template_vmid: Number(templateSelect.value)})
    });
    message.textContent = "ВМ успешно создана и запущена";
    message.className = "success";
    await loadVMs();
  } catch (error) {
    message.textContent = error.message;
    message.className = "error";
  } finally {
    if (loadingOverlay) loadingOverlay.hidden = true;
    getVmButton.disabled = false;
    templateSelect.disabled = false;
  }
});

document.querySelector("#vms").addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const vmid = button.dataset.vmid;
  const action = button.dataset.action;
  button.disabled = true;
  try {
    await request(`/api/vms/${vmid}/${action}`, {method: "POST"});
    if (action === "delete") {
      message.textContent = "ВМ удалена";
      message.className = "success";
    }
    await loadVMs();
  } catch (error) {
    message.textContent = error.message;
    message.className = "error";
    await loadVMs();
  } finally {
    button.disabled = false;
  }
});

async function loadCurrentUser() {
  const me = await request("/api/auth/me");
  passwordButton.hidden = !me.can_change_password;
}

function closePasswordDialog() {
  passwordOverlay.hidden = true;
  passwordForm.reset();
  passwordMessage.textContent = "";
  passwordMessage.className = "";
}

passwordButton.addEventListener("click", () => {
  passwordMessage.textContent = "";
  passwordMessage.className = "";
  passwordOverlay.hidden = false;
  passwordForm.querySelector("input").focus();
});
document.querySelector("#password-cancel").addEventListener("click", closePasswordDialog);
passwordOverlay.addEventListener("click", (event) => {
  if (event.target === passwordOverlay) closePasswordDialog();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !passwordOverlay.hidden) closePasswordDialog();
});

passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = Object.fromEntries(new FormData(passwordForm));
  if (body.new_password !== body.confirm_password) {
    passwordMessage.textContent = "Пароли не совпадают";
    passwordMessage.className = "error";
    return;
  }
  const submit = passwordForm.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    await request("/api/auth/password", {
      method: "POST",
      body: JSON.stringify({current_password: body.current_password, new_password: body.new_password})
    });
    closePasswordDialog();
    message.textContent = "Пароль изменён";
    message.className = "success";
  } catch (error) {
    passwordMessage.textContent = error.message;
    passwordMessage.className = "error";
  } finally {
    submit.disabled = false;
  }
});

document.querySelector("#logout").addEventListener("click", () => { sessionStorage.removeItem("token"); location.href = "/login.html"; });
Promise.all([loadCurrentUser(), loadTemplates(), loadVMs()]).catch(error => {
  message.textContent = error.message;
  message.className = "error";
});
