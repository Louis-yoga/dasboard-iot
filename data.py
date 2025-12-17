import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.dates as mdates

# 1. Load Data
df = pd.read_csv("Laporan_Ayam_Bakar_Log.csv")
df["Timestamp"] = pd.to_datetime(df["Timestamp"])  # Pastikan format waktu benar

# Atur Style Visualisasi
sns.set_style("whitegrid")

# 2. Visualisasi Time Series (Gas, Suhu, FQI)
fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

# Plot Gas
sns.lineplot(data=df, x="Timestamp", y="Gas", ax=axes[0], color="blue")
axes[0].set_title("Tren Level Gas")

# Plot Suhu
sns.lineplot(data=df, x="Timestamp", y="Temp", ax=axes[1], color="orange")
axes[1].set_title("Tren Suhu (°C)")

# Plot FQI
sns.lineplot(data=df, x="Timestamp", y="FQI", ax=axes[2], color="green")
axes[2].set_title("Tren Food Quality Index (FQI)")

# Format tanggal agar rapi
axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
plt.tight_layout()
plt.show()

# 3. Visualisasi Scatter Plot (Hubungan Gas vs FQI)
plt.figure(figsize=(10, 6))
sns.scatterplot(data=df, x="Gas", y="FQI", hue="Status", palette="viridis", s=60)
plt.title("Hubungan Gas vs FQI (Warna = Status)")
plt.show()

# 4. Visualisasi Distribusi Status
plt.figure(figsize=(8, 5))
sns.countplot(data=df, x="Status", palette="Reds")
plt.title("Jumlah Data per Status")
plt.show()
