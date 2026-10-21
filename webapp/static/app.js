const state = {
  customers: [],
  selectedCustomerId: null,
};

async function api(path, options) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.description || `${resp.status} ${resp.statusText}`);
  }
  return resp.status === 204 ? null : resp.json();
}

async function loadConfig() {
  const badge = document.getElementById("config-badge");
  try {
    const cfg = await api("/api/config");
    badge.textContent = cfg.real_model_available ? `real: ${cfg.default_model}` : "mock only (no API key)";
  } catch (err) {
    badge.textContent = "config unavailable";
  }
}

function renderCustomerList() {
  const list = document.getElementById("customer-list");
  list.innerHTML = "";

  const all = document.createElement("li");
  all.textContent = "All customers";
  all.className = state.selectedCustomerId === null ? "active" : "";
  all.addEventListener("click", () => selectCustomer(null));
  list.appendChild(all);

  for (const customer of state.customers) {
    const li = document.createElement("li");
    li.textContent = `${customer.customer_id} - ${customer.name}`;
    li.className = customer.customer_id === state.selectedCustomerId ? "active" : "";
    li.addEventListener("click", () => selectCustomer(customer.customer_id));
    list.appendChild(li);
  }
}

function renderCustomerSelects() {
  const submitSelect = document.getElementById("submit-customer");
  submitSelect.innerHTML = state.customers
    .map((c) => `<option value="${c.customer_id}">${c.customer_id} - ${c.name}</option>`)
    .join("");
}

function selectCustomer(customerId) {
  state.selectedCustomerId = customerId;
  renderCustomerList();
}

async function loadCustomers() {
  state.customers = await api("/api/customers");
  renderCustomerList();
  renderCustomerSelects();
}

async function init() {
  await loadConfig();
  await loadCustomers();
}

document.addEventListener("DOMContentLoaded", init);
