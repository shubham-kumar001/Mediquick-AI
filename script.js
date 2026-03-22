// ============================================
// MEDIMIND AI - FRONTEND SCRIPT
// ============================================

let currentUser = null;

const chatMessages = document.getElementById("chat-messages");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");

const SERIOUS_KEYWORDS = [
    "chest pain",
    "difficulty breathing",
    "shortness of breath",
    "trouble breathing",
    "severe pain",
    "unconscious",
    "fainting",
    "stroke",
    "heart attack",
    "blood vomiting",
    "vomiting blood",
    "seizure",
    "high fever",
    "persistent fever",
    "pregnancy complication"
];

async function sendMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    addUserMessage(message);
    chatInput.value = "";
    addTypingIndicator();

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message,
                user_id: currentUser?.id
            })
        });

        const data = await response.json();
        removeTypingIndicator();

        if (!data.success) {
            addBotMessage("I could not process that right now. Please try again.");
            return;
        }

        renderMedicalResponse(message, data.response, data.ml_analysis || {});
    } catch (error) {
        removeTypingIndicator();
        addBotMessage("Network error. Please check your connection.");
    }
}

function renderMedicalResponse(userMessage, botText, analysis) {
    const serious = isSeriousIssue(userMessage, analysis, botText);
    const summary = buildSummaryList(analysis);
    const actionLabel = serious ? "Book Appointment Now" : "View Doctors";
    const adviceLabel = serious
        ? "This may need timely medical attention. Please connect with a doctor."
        : "If symptoms continue or worsen, book a consultation for a proper diagnosis.";

    const messageDiv = document.createElement("div");
    messageDiv.className = "message bot";
    messageDiv.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content medical-response ${serious ? "serious" : ""}">
            <div class="message-text">${formatMessage(botText)}</div>
            ${summary ? `<div class="medical-summary">${summary}</div>` : ""}
            <div class="medical-guidance">
                <div class="guidance-badge ${serious ? "high-risk" : "watchful"}">
                    ${serious ? "Medical Attention Recommended" : "Monitor Symptoms"}
                </div>
                <p>${adviceLabel}</p>
            </div>
            <div class="chat-actions">
                <button class="chat-action-btn primary" data-action="appointments">${actionLabel}</button>
                <button class="chat-action-btn secondary" data-action="doctors">Find Doctors</button>
            </div>
        </div>
    `;

    const buttons = messageDiv.querySelectorAll(".chat-action-btn");
    buttons.forEach((button) => {
        button.addEventListener("click", () => {
            const action = button.dataset.action;
            if (action === "appointments") {
                if (!currentUser) {
                    showLoginModal();
                    return;
                }
                switchPage("appointments");
                loadAppointments();
                return;
            }

            switchPage("doctors");
            loadDoctors();
        });
    });

    chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

function buildSummaryList(analysis) {
    const items = [];

    if (analysis.disease) {
        const confidence = Number(analysis.disease_confidence || 0);
        items.push(`<li><strong>Likely condition:</strong> ${escapeHtml(String(analysis.disease))} (${confidence.toFixed(1)}% confidence)</li>`);
    }

    if (analysis.supportive_care?.supportive) {
        items.push(`<li><strong>Home care:</strong> ${escapeHtml(analysis.supportive_care.supportive)}</li>`);
    }

    if (analysis.diet_plan?.recommended_foods) {
        items.push(`<li><strong>Diet:</strong> ${escapeHtml(truncateText(analysis.diet_plan.recommended_foods, 120))}</li>`);
    }

    if (Array.isArray(analysis.lab_tests) && analysis.lab_tests.length > 0) {
        const firstTest = analysis.lab_tests[0]?.test_name || analysis.lab_tests[0];
        items.push(`<li><strong>Suggested test:</strong> ${escapeHtml(String(firstTest))}</li>`);
    }

    if (!items.length) return "";
    return `<ul>${items.join("")}</ul>`;
}

function isSeriousIssue(userMessage, analysis, botText) {
    const text = `${userMessage} ${botText} ${analysis?.disease || ""}`.toLowerCase();

    if (SERIOUS_KEYWORDS.some((keyword) => text.includes(keyword))) {
        return true;
    }

    const confidence = Number(analysis?.disease_confidence || 0);
    const disease = String(analysis?.disease || "").toLowerCase();
    const severeDiseaseHints = ["stroke", "cardiac", "cancer", "sepsis", "pneumonia", "kidney", "liver", "meningitis"];

    return confidence >= 35 && severeDiseaseHints.some((hint) => disease.includes(hint));
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return `${text.slice(0, maxLength).trim()}...`;
}

function addUserMessage(text) {
    const messageDiv = document.createElement("div");
    messageDiv.className = "message user";
    messageDiv.innerHTML = `
        <div class="message-avatar">You</div>
        <div class="message-content">
            <div class="message-text">${escapeHtml(text)}</div>
        </div>
    `;
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

function addBotMessage(text) {
    const messageDiv = document.createElement("div");
    messageDiv.className = "message bot";
    messageDiv.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content">
            <div class="message-text">${formatMessage(text)}</div>
        </div>
    `;
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
}

function addTypingIndicator() {
    const indicator = document.createElement("div");
    indicator.className = "message bot";
    indicator.id = "typing-indicator";
    indicator.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content">
            <div class="message-text">Analyzing your symptoms...</div>
        </div>
    `;
    chatMessages.appendChild(indicator);
    scrollToBottom();
}

function removeTypingIndicator() {
    const indicator = document.getElementById("typing-indicator");
    if (indicator) indicator.remove();
}

function formatMessage(text) {
    return escapeHtml(String(text))
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.*?)\*/g, "<em>$1</em>")
        .replace(/\n/g, "<br>");
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function loadDoctors() {
    const doctorsList = document.getElementById("doctors-list");
    doctorsList.innerHTML = '<div class="loading-spinner">Loading doctors...</div>';

    try {
        const response = await fetch("/api/doctors");
        const data = await response.json();

        if (data.doctors && data.doctors.length > 0) {
            doctorsList.innerHTML = data.doctors.map((doctor) => `
                <div class="doctor-card" data-doctor-id="${doctor.id}">
                    <h3>Dr. ${doctor.name}</h3>
                    <div class="doctor-specialization">${doctor.specialization || "General Physician"}</div>
                    <div class="doctor-details">
                        ${doctor.qualification ? `${doctor.qualification}<br>` : ""}
                        ${doctor.experience_years ? `${doctor.experience_years} years experience<br>` : ""}
                        Fee: Rs. ${doctor.consultation_fee || 500}
                    </div>
                    <div class="doctor-rating">Rating: ${doctor.rating || "4.5"} / 5</div>
                    <button class="book-btn" onclick="bookDoctor(${doctor.id}, '${doctor.name}')">Book Appointment</button>
                </div>
            `).join("");
        } else {
            doctorsList.innerHTML = "<p>No doctors found. Check back later.</p>";
        }
    } catch (error) {
        doctorsList.innerHTML = "<p>Error loading doctors. Please try again.</p>";
    }
}

async function bookDoctor(doctorId, doctorName) {
    if (!currentUser) {
        alert("Please login to book appointments");
        showLoginModal();
        return;
    }

    const date = prompt("Enter appointment date (YYYY-MM-DD):");
    const time = prompt("Enter appointment time (e.g., 10:00 AM):");

    if (!date || !time) return;

    try {
        const response = await fetch("/api/appointments", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: currentUser.id,
                doctor_id: doctorId,
                date,
                time
            })
        });

        const data = await response.json();
        if (data.success) {
            alert(`Appointment booked with Dr. ${doctorName} on ${date} at ${time}`);
            loadAppointments();
            switchPage("appointments");
        } else {
            alert(`Failed to book appointment: ${data.error}`);
        }
    } catch (error) {
        alert("Network error. Please try again.");
    }
}

async function loadAppointments() {
    if (!currentUser) {
        document.getElementById("appointments-list").innerHTML = "<p>Please login to view appointments</p>";
        return;
    }

    try {
        const response = await fetch(`/api/appointments/${currentUser.id}`);
        const data = await response.json();

        if (data.appointments && data.appointments.length > 0) {
            document.getElementById("appointments-list").innerHTML = data.appointments.map((apt) => `
                <div class="appointment-card">
                    <div>
                        <strong>${apt.doctor_name || apt.patient_name}</strong><br>
                        Date: ${apt.date} at ${apt.time}<br>
                        Notes: ${apt.notes || "No notes"}
                    </div>
                    <div>
                        <span class="appointment-status status-${apt.status}">${apt.status.toUpperCase()}</span>
                    </div>
                </div>
            `).join("");
        } else {
            document.getElementById("appointments-list").innerHTML = "<p>No appointments found</p>";
        }
    } catch (error) {
        document.getElementById("appointments-list").innerHTML = "<p>Error loading appointments</p>";
    }
}

function setupPrescriptionUpload() {
    const uploadArea = document.getElementById("upload-area");
    const fileInput = document.getElementById("prescription-file");
    const uploadBtn = document.getElementById("upload-btn");

    uploadArea.addEventListener("click", () => fileInput.click());
    uploadBtn.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append("file", file);

        document.getElementById("prescription-result").style.display = "block";
        document.getElementById("medicine-list").innerHTML = "<li>Processing prescription...</li>";

        try {
            const response = await fetch("/api/upload-prescription", {
                method: "POST",
                body: formData
            });

            const data = await response.json();

            if (data.success && data.extracted_medicines) {
                document.getElementById("medicine-list").innerHTML = data.extracted_medicines
                    .map((med) => `<li>${escapeHtml(med)}</li>`)
                    .join("");
            } else {
                document.getElementById("medicine-list").innerHTML = "<li>Could not extract medicines. Please try again.</li>";
            }
        } catch (error) {
            document.getElementById("medicine-list").innerHTML = "<li>Error processing prescription</li>";
        }
    });
}

async function checkAuth() {
    try {
        const response = await fetch("/api/auth/me");
        if (response.ok) {
            currentUser = await response.json();
            updateUIForLoggedInUser();
        } else {
            updateUIForLoggedOutUser();
        }
    } catch (error) {
        updateUIForLoggedOutUser();
    }
}

function updateUIForLoggedInUser() {
    document.getElementById("user-name").textContent = currentUser.name;
    document.getElementById("user-role").textContent = currentUser.role;
    document.getElementById("login-btn").style.display = "none";
    document.getElementById("logout-btn").style.display = "block";
    document.getElementById("user-avatar").textContent = currentUser.name.charAt(0).toUpperCase();
}

function updateUIForLoggedOutUser() {
    currentUser = null;
    document.getElementById("user-name").textContent = "Guest";
    document.getElementById("user-role").textContent = "Not logged in";
    document.getElementById("login-btn").style.display = "block";
    document.getElementById("logout-btn").style.display = "none";
    document.getElementById("user-avatar").textContent = "G";
}

async function login(email, password) {
    try {
        const response = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });

        const data = await response.json();
        if (response.ok) {
            currentUser = data.user;
            updateUIForLoggedInUser();
            closeModals();
            addBotMessage(`Welcome back, ${currentUser.name}. Tell me your symptoms and I will guide you.`);
            loadAppointments();
            return true;
        }

        alert(data.error);
        return false;
    } catch (error) {
        alert("Login failed. Please try again.");
        return false;
    }
}

async function signup(name, email, password, role) {
    try {
        const response = await fetch("/api/auth/signup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, email, password, role })
        });

        const data = await response.json();
        if (response.ok) {
            alert("Account created successfully! Please login.");
            showLoginModal();
            return true;
        }

        alert(data.error);
        return false;
    } catch (error) {
        alert("Signup failed. Please try again.");
        return false;
    }
}

async function logout() {
    try {
        await fetch("/api/auth/logout", { method: "POST" });
        updateUIForLoggedOutUser();
        addBotMessage("You have been logged out. Login again to book appointments.");
        loadAppointments();
    } catch (error) {
        console.error("Logout error:", error);
    }
}

function showLoginModal() {
    document.getElementById("login-modal").style.display = "flex";
    document.getElementById("login-email").focus();
}

function showSignupModal() {
    document.getElementById("signup-modal").style.display = "flex";
}

function closeModals() {
    document.getElementById("login-modal").style.display = "none";
    document.getElementById("signup-modal").style.display = "none";
}

function switchPage(pageId) {
    document.querySelectorAll(".page").forEach((page) => {
        page.classList.remove("active");
    });
    document.getElementById(`${pageId}-page`).classList.add("active");

    document.querySelectorAll(".nav-item").forEach((item) => {
        item.classList.remove("active");
        if (item.dataset.page === pageId) {
            item.classList.add("active");
        }
    });

    if (pageId === "doctors") loadDoctors();
    if (pageId === "appointments") loadAppointments();
}

sendBtn.addEventListener("click", sendMessage);
chatInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", (e) => {
        e.preventDefault();
        switchPage(item.dataset.page);
    });
});

document.getElementById("login-btn").addEventListener("click", showLoginModal);
document.getElementById("logout-btn").addEventListener("click", logout);
document.getElementById("show-signup").addEventListener("click", (e) => {
    e.preventDefault();
    closeModals();
    showSignupModal();
});
document.getElementById("show-login").addEventListener("click", (e) => {
    e.preventDefault();
    closeModals();
    showLoginModal();
});

document.getElementById("login-submit").addEventListener("click", async () => {
    const email = document.getElementById("login-email").value;
    const password = document.getElementById("login-password").value;
    if (await login(email, password)) {
        closeModals();
    }
});

document.getElementById("signup-submit").addEventListener("click", async () => {
    const name = document.getElementById("signup-name").value;
    const email = document.getElementById("signup-email").value;
    const password = document.getElementById("signup-password").value;
    const role = document.getElementById("signup-role").value;

    if (!name || !email || !password) {
        alert("Please fill all fields");
        return;
    }

    if (password.length < 6) {
        alert("Password must be at least 6 characters");
        return;
    }

    if (await signup(name, email, password, role)) {
        closeModals();
    }
});

document.querySelectorAll(".close-modal").forEach((btn) => {
    btn.addEventListener("click", closeModals);
});

window.addEventListener("click", (e) => {
    if (e.target.classList.contains("modal")) {
        closeModals();
    }
});

setupPrescriptionUpload();
checkAuth();
