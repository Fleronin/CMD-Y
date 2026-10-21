const state = {
  customers: [],
  tickets: [],
  selectedCustomerId: null,
  selectedTicketId: null,
};

async function api(path, options) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.description || `${resp.status} ${resp.statusText}`);
  }
  return resp.status === 204 ? null : resp.json();
}

// Ticket subjects/bodies are attacker-controlled (that's the whole point of
// this project), so anything from them goes through this before it lands in
// innerHTML rather than being trusted as markup.
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
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

async function selectCustomer(customerId) {
  state.selectedCustomerId = customerId;
  renderCustomerList();
  await loadTickets();
}

async function loadCustomers() {
  state.customers = await api("/api/customers");
  renderCustomerList();
  renderCustomerSelects();
}

function renderTicketList() {
  const heading = document.getElementById("tickets-heading");
  heading.textContent = state.selectedCustomerId ? `Tickets for ${state.selectedCustomerId}` : "All tickets";

  const list = document.getElementById("ticket-list");
  list.innerHTML = "";
  for (const ticket of state.tickets) {
    const li = document.createElement("li");
    li.className = ticket.ticket_id === state.selectedTicketId ? "active" : "";
    li.innerHTML = `
      <span class="ticket-subject">${escapeHtml(ticket.subject)}</span>
      <span class="ticket-meta">${ticket.ticket_id} - ${ticket.customer_id} - ${ticket.status}</span>
    `;
    li.addEventListener("click", () => selectTicket(ticket.ticket_id));
    list.appendChild(li);
  }
}

async function loadTickets() {
  const query = state.selectedCustomerId ? `?customer_id=${encodeURIComponent(state.selectedCustomerId)}` : "";
  state.tickets = await api(`/api/tickets${query}`);
  renderTicketList();
}

function renderAttachment(att) {
  return `
    <li>
      <strong>${escapeHtml(att.filename)}</strong>
      <span class="ticket-meta">title: ${escapeHtml(att.metadata?.title)} - author: ${escapeHtml(att.metadata?.author)}</span>
      <pre>${escapeHtml(att.extracted_text)}</pre>
    </li>
  `;
}

function renderNote(note) {
  return `
    <li>
      <span class="ticket-meta">${escapeHtml(note.author)} - ${escapeHtml(note.created_at)}</span>
      <p>${escapeHtml(note.text)}</p>
    </li>
  `;
}

function renderReply(reply) {
  return `
    <li>
      <span class="ticket-meta">${escapeHtml(reply.created_at)}</span>
      <p>${escapeHtml(reply.message)}</p>
    </li>
  `;
}

function renderTicketDetail(ticket) {
  const detail = document.getElementById("ticket-detail");
  detail.innerHTML = `
    <h2>${escapeHtml(ticket.ticket_id)}: ${escapeHtml(ticket.subject)}</h2>
    <p class="ticket-meta">${escapeHtml(ticket.customer_id)} - ${escapeHtml(ticket.status)} - ${escapeHtml(ticket.created_at)}</p>
    <h3>Body</h3>
    <pre>${escapeHtml(ticket.body)}</pre>
    ${ticket.attachments.length ? `<h3>Attachments</h3><ul>${ticket.attachments.map(renderAttachment).join("")}</ul>` : ""}
    ${ticket.notes.length ? `<h3>Notes</h3><ul>${ticket.notes.map(renderNote).join("")}</ul>` : ""}
    ${ticket.replies.length ? `<h3>Replies</h3><ul>${ticket.replies.map(renderReply).join("")}</ul>` : ""}
  `;
}

function populateRunSubmitter(defaultCustomerId) {
  const select = document.getElementById("run-submitter");
  select.innerHTML = state.customers
    .map((c) => `<option value="${c.customer_id}">${c.customer_id} - ${c.name}</option>`)
    .join("");
  select.value = defaultCustomerId;
}

async function selectTicket(ticketId) {
  state.selectedTicketId = ticketId;
  renderTicketList();

  const ticket = await api(`/api/tickets/${encodeURIComponent(ticketId)}`);
  renderTicketDetail(ticket);
  populateRunSubmitter(ticket.customer_id);
  document.getElementById("run-panel").hidden = false;
  document.getElementById("run-result").innerHTML = "";
}

async function init() {
  await loadConfig();
  await loadCustomers();
  await loadTickets();
}

document.addEventListener("DOMContentLoaded", init);
