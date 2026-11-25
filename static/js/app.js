document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".role-toggle button").forEach(button => {
    button.addEventListener("click", () => {
      const role = button.dataset.role;
      document.querySelectorAll(".role-toggle button").forEach(b => b.classList.toggle("active", b === button));
      const form = document.querySelector("#login-form");
      if (form) form.action = "/" + role + "/login";
    });
  });
  const show = document.querySelector("#show-password");
  if (show) show.addEventListener("click", () => {
    const password = document.querySelector("#password");
    const visible = password.type === "text";
    password.type = visible ? "password" : "text";
    show.textContent = visible ? "Show" : "Hide";
  });
  const uploadForm = document.querySelector("#upload-form");
  if (uploadForm) {
    uploadForm.addEventListener("submit", () => {
      const button = uploadForm.querySelector('button[type="submit"]');
      const message = document.querySelector("#upload-message");
      button.disabled = true;
      button.textContent = "Uploading…";
      if (message) message.textContent = "Your files are being uploaded.";
    });
  }
  let count = 1;
  const add = document.querySelector("#add-question");
  const remove = document.querySelector("#remove-question");
  const list = document.querySelector("#question-list");
  const counter = document.querySelector("#question-count");
  if (add && list) {
    add.addEventListener("click", () => {
      if (count >= 20) return;
      count++;
      const block = document.createElement("div");
      block.className = "question-block";
      block.innerHTML = `<label>Question ${count}</label><textarea name="question_${count-1}" required></textarea><label>Max marks <input type="number" name="marks_${count-1}" value="10" min="0.5" step="0.5"></label>`;
      list.appendChild(block); counter.textContent = count;
    });
  }
  if (remove && list) remove.addEventListener("click", () => {
    if (count <= 1) return;
    list.lastElementChild.remove(); count--; counter.textContent = count;
  });
});
