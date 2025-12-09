const ACTIVE_DEVICE_ID = "ESP32_REAL_01";

// --- SETUP CHART (GRAFIK) ---
const ctx = document.getElementById('mainChart').getContext('2d');
const mainChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [{
            label: 'Skor Kualitas (FQI)',
            data: [],
            borderColor: '#0d6efd',
            backgroundColor: 'rgba(13, 110, 253, 0.1)',
            tension: 0.4,
            fill: true
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 0 },
        scales: {
            y: {
                min: 0,
                max: 100,
                grid: { color: '#f0f0f0' }
            },
            x: {
                grid: { display: false }
            }
        },
        plugins: {
            legend: { display: false }
        }
    }
});

// --- FUNGSI TOMBOL POWER (SAKLAR) ---
async function togglePower() {
    try {
        await fetch(`/api/device/${ACTIVE_DEVICE_ID}/toggle`, { method: 'POST' });
    } catch (error) {
        console.error("Gagal toggle power", error);
    }
}

// --- FUNGSI 1: Ambil Data Sensor (Real-time) ---
async function fetchData() {
    try {
        const response = await fetch(`/api/latest/${ACTIVE_DEVICE_ID}`);
        if (!response.ok) return;

        const data = await response.json();

        // --- UPDATE STATUS TOMBOL POWER ---
        const powerSwitch = document.getElementById('powerSwitch');
        const powerLabel = document.getElementById('powerLabel');

        if (powerSwitch) {
            if (powerSwitch.checked !== data.is_active) {
                powerSwitch.checked = data.is_active;
            }
            powerLabel.innerText = data.is_active ? "ON" : "OFF";
            powerLabel.className = data.is_active ? "form-check-label fw-bold text-success" : "form-check-label fw-bold text-muted";
        }

        // --- LOGIKA UTAMA: CEK APAKAH ALAT HIDUP ATAU MATI ---
        if (!data.is_active) {
            // === JIKA ALAT MATI (OFF) ===
            // 1. Kosongkan semua tampilan angka
            document.getElementById('fqiValue').innerText = "--";
            document.getElementById('mqValue').innerText = "-";
            document.getElementById('tempValue').innerText = "-";
            document.getElementById('currentProfileName').innerText = "System Off";

            // 2. Kosongkan Estimasi Waktu
            const estElement = document.getElementById('estTimeValue');
            if (estElement) estElement.innerText = "Non-Aktif";

            // 3. Ubah Badge Status jadi Abu-abu
            const badge = document.getElementById('statusBadge');
            badge.innerText = "ALAT MATI";
            badge.className = "badge bg-secondary fs-5 px-4 py-2";

            // 4. Update Koneksi tapi statusnya Standby
            document.getElementById('connectionStatus').innerText = "● Standby";
            document.getElementById('connectionStatus').className = "navbar-text text-warning fw-bold";

            return;
        }

        // === JIKA ALAT HIDUP (ON) - LANJUTKAN SEPERTI BIASA ===

        // 1. Update Angka
        document.getElementById('fqiValue').innerText = data.fqi;
        document.getElementById('mqValue').innerText = Math.round(data.mq135) + " ppm";
        document.getElementById('tempValue').innerText = data.temp + " °C";
        document.getElementById('currentProfileName').innerText = data.current_profile || "Unknown";

        // Update Estimasi
        const estElement = document.getElementById('estTimeValue');
        if (estElement) estElement.innerText = data.estimated_life || "-";

        // 2. Update Warna Badge
        const badge = document.getElementById('statusBadge');
        badge.innerText = data.status;

        if (data.status.toUpperCase().includes("BASI") || data.status.toUpperCase().includes("BERBAHAYA")) {
            badge.className = "badge bg-danger fs-5 px-4 py-2";
        } else if (data.status.includes("Mulai")) {
            badge.className = "badge bg-warning text-dark fs-5 px-4 py-2";
        } else {
            badge.className = "badge bg-success fs-5 px-4 py-2";
        }

        // 3. Update Grafik
        const timeLabel = data.timestamp;
        if (mainChart.data.labels[mainChart.data.labels.length - 1] !== timeLabel) {
            if (mainChart.data.labels.length > 20) {
                mainChart.data.labels.shift();
                mainChart.data.datasets[0].data.shift();
            }
            mainChart.data.labels.push(timeLabel);
            mainChart.data.datasets[0].data.push(data.fqi);
            mainChart.update();
        }

        document.getElementById('connectionStatus').innerText = "● Connected";
        document.getElementById('connectionStatus').className = "navbar-text text-white fw-bold";

    } catch (error) {
        console.log("Waiting...", error);
        document.getElementById('connectionStatus').innerText = "○ Disconnected";
        document.getElementById('connectionStatus').className = "navbar-text text-white-50";
    }
}

// --- FUNGSI 2: Load Daftar Profil ke Dropdown ---
async function loadProfiles() {
    try {
        const response = await fetch('/api/profiles');
        const profiles = await response.json();

        const select = document.getElementById('profileSelect');
        select.innerHTML = ""; // Bersihkan opsi lama

        profiles.forEach(p => {
            const option = document.createElement('option');
            option.value = p.id;
            option.text = p.name;
            select.appendChild(option);
        });
    } catch (error) {
        console.error("Gagal load profile", error);
    }
}

// --- FUNGSI 3: Kirim Perintah Ganti Profil ---
async function changeProfile() {
    const select = document.getElementById('profileSelect');
    const profileId = select.value;

    if (!profileId) return;

    try {
        const response = await fetch(`/api/device/${ACTIVE_DEVICE_ID}/set_profile`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile_id: profileId })
        });

        if (response.ok) {
            alert("Profil berhasil diganti! Perhitungan FQI berikutnya akan menyesuaikan.");
        } else {
            alert("Gagal mengganti profil.");
        }
    } catch (error) {
        alert("Error koneksi.");
    }
}

// --- FUNGSI 4: Update Tabel History (Dengan Kolom Estimasi) ---
async function updateHistoryTable() {
    try {
        const response = await fetch(`/api/history/${ACTIVE_DEVICE_ID}`);
        if (!response.ok) return;

        const data = await response.json();
        const tbody = document.getElementById('historyTableBody');
        tbody.innerHTML = "";

        if (data.length === 0) {
            tbody.innerHTML = "<tr><td colspan='7'>Belum ada data terekam.</td></tr>";
            return;
        }

        data.forEach(row => {
            // Tentukan warna status untuk tabel
            let badgeClass = "bg-secondary";
            if (row.status.toUpperCase().includes("BASI") || row.status.toUpperCase().includes("BERBAHAYA")) {
                badgeClass = "bg-danger";
            } else if (row.status.includes("Mulai")) {
                badgeClass = "bg-warning text-dark";
            } else {
                badgeClass = "bg-success";
            }

            const tr = `
                <tr>
                    <td>${row.timestamp}</td>
                    <td><span class="badge bg-info text-dark">${row.food_name || '-'}</span></td>
                    <td>${Math.round(row.mq135)}</td>
                    <td>${row.temp}</td>
                    <td><strong>${row.fqi}</strong></td>
                    <td><span class="badge ${badgeClass}">${row.status}</span></td>
                    <td class="fw-bold text-primary">${row.estimated_life || '-'}</td>
                </tr>
            `;
            tbody.innerHTML += tr;
        });

    } catch (error) {
        console.error("Gagal load history:", error);
    }
}

// --- FUNGSI 5: Download CSV ---
function downloadCSV() {
    window.location.href = `/api/export/${ACTIVE_DEVICE_ID}`;
}

// --- INISIALISASI ---
loadProfiles();
setInterval(fetchData, 3000);
setInterval(updateHistoryTable, 5000);
fetchData();
updateHistoryTable();