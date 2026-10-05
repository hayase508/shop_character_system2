"use strict";
async function request(url, method = "POST") {
  try {
    const response = await fetch(url, { method });
    document.getElementById("result").textContent =
      response.status + "\n" + JSON.stringify(await response.json(), null, 2);
  } catch (error) { document.getElementById("result").textContent = String(error); }
}
document.querySelectorAll("[data-url]").forEach(button => {
  button.addEventListener("click", () => void request(button.dataset.url));
});
document.getElementById("returning").addEventListener("click", () => {
  void request("/api/debug/returning-customer?days_since_last_visit=" +
    encodeURIComponent(document.getElementById("days").value));
});
document.getElementById("health").addEventListener("click", () => void request("/health", "GET"));
