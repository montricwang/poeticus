"use strict";
const $ = (selector) => document.querySelector(selector);
let csrfToken = "";
let current = "frontend";
let logFeed = null;
let refreshing = false;
let working = false;
let allServices = [];
let allConfigs = {};
let editingService = null;
let toastTimeout;
const names = {running:"运行中", starting:"启动中", stopped:"已停止", external:"外部运行"};
const output = $("#output");

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("visible");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => element.classList.remove("visible"), 4000);
}

function appendLog(text) {
  output.textContent += text;
  if (output.textContent.length > 110000) output.textContent = output.textContent.slice(-85000);
  $("#log-size").textContent = output.textContent.split("\n").length + " lines";
  if ($("#follow").checked) output.scrollTop = output.scrollHeight;
}

function switchLog(key) {
  current = key;
  $("#log-select").value = key;
  if (logFeed) logFeed.close();
  output.textContent = "";
  $("#log-size").textContent = "0 lines";
  $("#log-hint").textContent = key === "mcp" ? "MCP 巡检日志 · 其余四条 Worker 日志由原管理器保存" : "持续读取本地日志文件 · SSE";
  logFeed = new EventSource("/api/services/" + key + "/events");
  logFeed.onmessage = (event) => {
    try { appendLog(JSON.parse(event.data).text); } catch (error) { console.error(error); }
  };
  logFeed.onerror = () => { $("#log-hint").textContent = "日志连接断开 · 正在自动重连"; };
  document.querySelectorAll(".service").forEach(card => card.classList.toggle("selected", card.dataset.id === key));
}

async function api(path, method = "GET") {
  const headers = method === "GET" ? {} : {"X-Console-Token":csrfToken};
  const response = await fetch(path, { method, headers, cache:"no-store" });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "HTTP " + response.status);
  return body;
}

async function openSettings(key) {
  if (working) return;
  try {
    allConfigs = (await api("/api/config")).services;
    const data = allConfigs[key];
    editingService = key;
    const service = allServices.find(s => s.id === key);
    $("#settings-title").textContent = (service?.title || key) + " · 启动配置";
    const managed = Boolean(service?.managed);
    $("#settings-tip").textContent = managed
      ? "服务正在运行。可以查看启动定义；请先停止该服务再修改或恢复默认。"
      : "完整的启动定义。修改只影响下次启动，不会自动重启正在运行的服务。";
    $("#settings-save").disabled = managed;
    $("#settings-reset").disabled = managed;
    $("#port-field").hidden = data.port === null;
    $("#extra-field").hidden = key === "mcp" || key === "tunnel";
    $("#distro-field").hidden = data.platform !== "WSL";
    $("#script-field").hidden = key !== "mcp";
    $("#settings-port").required = data.port !== null;
    $("#settings-port").value = data.port ?? "";
    $("#settings-args").value = data.arguments;
    $("#settings-platform").value = data.platform;
    $("#settings-distro").value = data.distro;
    $("#settings-program").value = data.program;
    $("#settings-command-args").value = data.command_args;
    $("#settings-command-args").readOnly = key === "mcp" || key === "tunnel";
    $("#settings-working-dir").value = data.working_directory;
    $("#settings-init").value = data.initialization;
    $("#settings-init").disabled = data.platform === "Windows";
    $("#settings-script-path").value = data.script_path;
    $("#settings-preview").textContent = data.preview;
    $("#settings-dialog").showModal();
  } catch (error) {
    toast("读取配置失败：" + error.message);
  }
}

async function saveSettings(event) {
  event.preventDefault();
  if (!editingService) return;
  const key = editingService;
  const isWSL = allConfigs[key].platform === "WSL";
  const value = {
    port: $("#settings-port").required ? Number($("#settings-port").value) : null,
    arguments: $("#extra-field").hidden ? "" : $("#settings-args").value.trim(),
    program: $("#settings-program").value.trim(),
    command_args: $("#settings-command-args").value.trim(),
    working_directory: $("#settings-working-dir").value.trim(),
    initialization: isWSL ? $("#settings-init").value : "none",
    distro: isWSL ? $("#settings-distro").value.trim() : "",
    script_path: key === "mcp" ? $("#settings-script-path").value.trim() : ""
  };
  try {
    const response = await fetch("/api/config/" + key, {
      method:"POST",
      headers: {"X-Console-Token":csrfToken,"Content-Type":"application/json"},
      body:JSON.stringify(value)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "保存失败");
    $("#settings-dialog").close();
    editingService = null;
    toast("配置已保存；下次启动时生效");
    await refresh();
  } catch (error) {
    toast("保存失败：" + error.message);
  }
}

async function resetSettings() {
  const key = editingService;
  if (!key || !confirm("恢复这项服务的默认启动配置？不会改变其他服务。")) return;
  try {
    const result = await api("/api/config/" + key + "/reset", "POST");
    allConfigs[key] = result.settings;
    $("#settings-dialog").close();
    editingService = null;
    toast("已恢复默认配置");
    await refresh();
  } catch (error) {
    toast("恢复失败：" + error.message);
  }
}

function button(label, action, key, disabled) {
  const btn = document.createElement("button");
  btn.className = "btn-mini" + (action === "stop" ? " btn-stop" : "");
  btn.textContent = label;
  btn.disabled = disabled || working;
  btn.addEventListener("click", async (event) => {
    event.stopPropagation();
    await act(key, action);
  });
  return btn;
}

function renderServices() {
  const target = $("#services");
  target.replaceChildren();
  for (const service of allServices) {
    const card = document.createElement("div");
    card.className = "service" + (service.id === current ? " selected" : "");
    card.dataset.id = service.id;
    card.setAttribute("role", "group");
    card.tabIndex = 0;
    const main = document.createElement("div"); main.className = "svc-main";
    const icon = document.createElement("div"); icon.className = "service-icon";
    icon.textContent = {frontend:"FE", backend:"BE", langgraph:"AG", retrieval:"RG", reranker:"LL", tunnel:"CF", mcp:"MC"}[service.id];
    const description = document.createElement("div");
    const title = document.createElement("div"); title.className = "svc-title"; title.textContent = service.title;
    const meta = document.createElement("div"); meta.className = "svc-meta";
    meta.textContent = service.environment + (service.port ? " · :" + service.port : "") + (service.pid ? " · PID " + service.pid : "");
    description.append(title,meta); main.append(icon,description);
    const control = document.createElement("div"); control.className = "svc-control";
    const state = document.createElement("span"); state.className = "status " + service.state;
    const dot = document.createElement("i"); dot.className = "dot";
    state.append(dot, document.createTextNode(names[service.state] || service.state));
    control.append(state);
    {
      const settings = document.createElement("button");
      settings.className = "btn-mini btn-settings";
      settings.textContent = "⚙";
      settings.title = "配置启动参数";
      settings.setAttribute("aria-label", "配置 " + service.title);
      settings.addEventListener("click", event => {
        event.stopPropagation();
        openSettings(service.id);
      });
      control.append(settings);
    }
    if (service.state === "stopped") control.append(button("启动", "start", service.id, false));
    if (service.managed) {
      control.append(button("重启", "restart", service.id, false));
      control.append(button("停止", "stop", service.id, false));
    }
    card.append(main,control);
    card.addEventListener("click", () => switchLog(service.id));
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.target === card) switchLog(service.id);
    });
    target.append(card);
  }
  const active = allServices.filter(s => s.state !== "stopped").length;
  $("#total").textContent = String(allServices.length).padStart(2,"0");
  $("#active").textContent = String(active).padStart(2,"0");
  $("#idle").textContent = String(allServices.length - active).padStart(2,"0");
}

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    allServices = (await api("/api/services")).services;
    const selection = $("#log-select");
    if (selection.options.length !== allServices.length) {
      selection.replaceChildren();
      for (const service of allServices) {
        const option = document.createElement("option");
        option.value = service.id;
        option.textContent = service.title;
        selection.append(option);
      }
      switchLog(current);
    }
    renderServices();
  } catch(error) {
    toast("状态获取失败：" + error.message);
  } finally {
    refreshing = false;
  }
}

async function act(key, action) {
  if (working) return;
  working = true; renderServices();
  try {
    const answer = await api("/api/services/" + key + "/" + action, "POST");
    toast(answer.message);
    await refresh();
  } catch(error) {
    toast("操作失败：" + error.message);
  } finally {
    working = false; renderServices();
  }
}

async function bulk(action) {
  if (working) return;
  if (action === "stop" && !confirm("确定停止控制台所管理的全部服务吗？外部进程不会被关闭。")) return;
  working = true;
  document.querySelectorAll("[data-all]").forEach(b => b.disabled = true);
  renderServices();
  try {
    const answer = await api("/api/all/" + action, "POST");
    const failed = Object.entries(answer.results).filter(([,msg]) => msg.startsWith("失败"));
    toast(failed.length ? failed.map(([key,msg])=> key+": "+msg).join("；") : "批量操作已完成");
    await refresh();
  } catch(error) {
    toast("批量操作失败：" + error.message);
  } finally {
    working = false;
    document.querySelectorAll("[data-all]").forEach(b => b.disabled = false);
    renderServices();
  }
}

async function init() {
  try {
    csrfToken = (await api("/api/token")).token;
    await refresh();
  } catch(error) {
    toast("无法连接本地管理器：" + error.message);
  }
  $("#settings-form").addEventListener("submit", saveSettings);
  $("#settings-reset").addEventListener("click", resetSettings);
  $("#settings-close").addEventListener("click", () => $("#settings-dialog").close());
  $("#settings-cancel").addEventListener("click", () => $("#settings-dialog").close());
  $("#settings-dialog").addEventListener("close", () => { editingService = null; });
  $("#refresh").addEventListener("click",refresh);
  $("#log-select").addEventListener("change", event => switchLog(event.target.value));
  $("#clear").addEventListener("click", () => {output.textContent = "";$("#log-size").textContent = "0 lines";});
  document.querySelectorAll("[data-all]").forEach(btn => btn.addEventListener("click",()=>bulk(btn.dataset.all)));
  function updateClock(){ $("#clock").textContent = new Date().toLocaleTimeString("zh-CN",{hour12:false}); }
  updateClock(); setInterval(updateClock,1000);
  setInterval(refresh,4500);
}
init();
