import streamlit as st
import simpy
import random
import pandas as pd
import numpy as np
import plotly.express as px

# ---------------------------------------------------------
# SİMÜLASYON SINIFI VE FONKSİYONLARI
# ---------------------------------------------------------
class AidSimulation:
    def __init__(self, target_boxes, distance, prod_range, 
                 food_time_range, food_qty_range, 
                 nonfood_time_range, nonfood_qty_range,
                 kamyon_range, tir_range, speed_range,
                 breakdown_dur_range, breakdown_int_range, accident_prob_range,
                 enable_logging=False):
        
        self.env = simpy.Environment()
        
        self.food_materials = simpy.Container(self.env, init=0, capacity=float('inf'))
        self.nonfood_materials = simpy.Container(self.env, init=0, capacity=float('inf'))
        self.finished_goods = simpy.Container(self.env, init=0, capacity=float('inf'))
        
        self.target_boxes = target_boxes
        self.distance = distance
        self.prod_range = prod_range
        self.food_time_range = food_time_range
        self.food_qty_range = food_qty_range
        self.nonfood_time_range = nonfood_time_range
        self.nonfood_qty_range = nonfood_qty_range
        
        self.kamyon_range = kamyon_range
        self.tir_range = tir_range
        self.speed_range = speed_range
        self.breakdown_dur_range = breakdown_dur_range
        self.breakdown_int_range = breakdown_int_range
        
        self.accident_rate = random.uniform(accident_prob_range[0], accident_prob_range[1]) / 100.0
        
        self.total_shipped = 0
        self.total_delivered = 0
        self.completion_event = self.env.event()
        self.is_under_maintenance = False
        
        self.accident_count = 0
        self.total_maintenance_time = 0
        self.total_produced = 0
        
        self.enable_logging = enable_logging
        self.logs = []

    def log_event(self, time, event_type, details):
        if self.enable_logging:
            self.logs.append({
                "Saat": round(time, 2),
                "Olay": event_type,
                "Detay": details,
                "Ulaşan Toplam Koli": self.total_delivered
            })

    def food_supplier_process(self):
        initial_supply = int(random.uniform(*self.food_qty_range))
        yield self.food_materials.put(initial_supply)
        self.log_event(self.env.now, "İlk Tedarik (Gıda)", f"{initial_supply} adet gıda içeriği stoka girdi.")

        while self.total_delivered < self.target_boxes:
            supply_interval = random.uniform(*self.food_time_range)
            yield self.env.timeout(supply_interval)
            supply_qty = int(random.uniform(*self.food_qty_range))
            yield self.food_materials.put(supply_qty)
            self.log_event(self.env.now, "Tedarik (Gıda)", f"{supply_qty} adet gıda stoka girdi. (Mevcut: {self.food_materials.level})")

    def nonfood_supplier_process(self):
        initial_supply = int(random.uniform(*self.nonfood_qty_range))
        yield self.nonfood_materials.put(initial_supply)
        self.log_event(self.env.now, "İlk Tedarik (Gıda Dışı)", f"{initial_supply} adet gıda dışı içerik stoka girdi.")

        while self.total_delivered < self.target_boxes:
            supply_interval = random.uniform(*self.nonfood_time_range)
            yield self.env.timeout(supply_interval)
            supply_qty = int(random.uniform(*self.nonfood_qty_range))
            yield self.nonfood_materials.put(supply_qty)
            self.log_event(self.env.now, "Tedarik (Gıda Dışı)", f"{supply_qty} adet gıda dışı stoka girdi. (Mevcut: {self.nonfood_materials.level})")

    def maintenance_process(self):
        while self.total_delivered < self.target_boxes:
            interval = random.uniform(*self.breakdown_int_range)
            if interval == 0:
                interval = 0.1 
            yield self.env.timeout(interval)
            
            duration_mins = random.uniform(*self.breakdown_dur_range)
            duration_hours = duration_mins / 60.0
            
            self.is_under_maintenance = True
            self.total_maintenance_time += duration_hours
            self.log_event(self.env.now, "Üretim Duruşu", f"Arıza/Bakım başladı. ({duration_mins:.0f} dk)")
            
            yield self.env.timeout(duration_hours)
            self.is_under_maintenance = False
            self.log_event(self.env.now, "Üretim Başladı", "Arıza/Bakım tamamlandı.")

    def production_process(self):
        while self.total_delivered < self.target_boxes:
            yield self.env.timeout(1)
            
            if self.is_under_maintenance:
                continue 
                
            current_capacity = int(random.uniform(*self.prod_range))
            available_materials = min(self.food_materials.level, self.nonfood_materials.level)
            
            if available_materials > 0:
                production_amount = min(current_capacity, available_materials)
                remaining_target = self.target_boxes - self.finished_goods.level - self.total_shipped
                
                if remaining_target <= 0:
                    continue
                    
                production_amount = min(production_amount, remaining_target)
                
                if production_amount > 0:
                    yield self.food_materials.get(production_amount)
                    yield self.nonfood_materials.get(production_amount)
                    yield self.finished_goods.put(production_amount)
                    self.total_produced += production_amount
                    self.log_event(self.env.now, "Üretim", f"{production_amount} koli üretildi. (Depo: {self.finished_goods.level})")

    def logistics_process(self):
        while self.total_delivered < self.target_boxes:
            yield self.env.timeout(1)
            
            remaining_to_ship = self.target_boxes - self.total_shipped
            if remaining_to_ship <= 0:
                continue
                
            tir_count = int(random.uniform(*self.tir_range))
            kamyon_count = int(random.uniform(*self.kamyon_range))
            
            for _ in range(tir_count):
                if self.finished_goods.level > 0 and self.total_shipped < self.target_boxes:
                    amount_to_load = min(1500, self.target_boxes - self.total_shipped, self.finished_goods.level)
                    if amount_to_load > 0:
                        yield self.finished_goods.get(amount_to_load)
                        self.total_shipped += amount_to_load
                        self.env.process(self.vehicle_delivery(amount_to_load, "Tır"))

            for _ in range(kamyon_count):
                if self.finished_goods.level > 0 and self.total_shipped < self.target_boxes:
                    amount_to_load = min(750, self.target_boxes - self.total_shipped, self.finished_goods.level)
                    if amount_to_load > 0:
                        yield self.finished_goods.get(amount_to_load)
                        self.total_shipped += amount_to_load
                        self.env.process(self.vehicle_delivery(amount_to_load, "Kamyon"))

    def vehicle_delivery(self, amount, vehicle_type):
        speed = random.uniform(*self.speed_range)
        travel_time = self.distance / speed
        
        self.log_event(self.env.now, "Sevkiyat Çıkışı", f"{amount} koli yüklü {vehicle_type} yola çıktı. (Hız: {speed:.1f} km/s)")
        
        if random.random() < self.accident_rate:
            yield self.env.timeout(travel_time / 2)
            self.accident_count += 1
            self.total_shipped -= amount
            self.log_event(self.env.now, "Kaza/İptal", f"{vehicle_type} kaza yaptı. {amount} koli teslim edilemedi.")
        else:
            yield self.env.timeout(travel_time)
            self.total_delivered += amount
            self.log_event(self.env.now, "Teslimat", f"{vehicle_type} ulaştı. Koli: {amount}")
            
            if self.total_delivered >= self.target_boxes:
                if not self.completion_event.triggered:
                    self.completion_event.succeed()

    def run(self):
        self.env.process(self.food_supplier_process())
        self.env.process(self.nonfood_supplier_process())
        self.env.process(self.maintenance_process())
        self.env.process(self.production_process())
        self.env.process(self.logistics_process())
        
        self.env.run(until=self.completion_event)
        return self.logs, self.env.now, self.accident_count, self.total_maintenance_time

# ---------------------------------------------------------
# STREAMLIT ÖN YÜZ (ARAYÜZ)
# ---------------------------------------------------------
st.set_page_config(page_title="Stokastik Lojistik Simülasyonu", layout="wide")

st.sidebar.header("Senaryo Parametreleri")
target_boxes_range = st.sidebar.slider("Gereken Koli Sayısı", min_value=10000, max_value=200000, value=(50000, 100000), step=1000)
distance_range = st.sidebar.slider("Mesafe (km)", min_value=50, max_value=750, value=(200, 400), step=10)
prod_capacity_range = st.sidebar.slider("Saatlik Üretim Kapasitesi", min_value=350, max_value=1500, value=(800, 1200), step=50)

st.sidebar.subheader("Gıda İçerik Tedariki")
food_supply_time_range = st.sidebar.slider("Gıda Temin Süresi (Saat)", min_value=1, max_value=72, value=(24, 48), step=1)
food_supply_qty_range = st.sidebar.slider("Gıda Temin Miktarı", min_value=1000, max_value=200000, value=(20000, 50000), step=1000)

st.sidebar.subheader("Gıda Dışı İçerik Tedariki")
nonfood_supply_time_range = st.sidebar.slider("Gıda Dışı Temin Süresi (Saat)", min_value=1, max_value=72, value=(24, 48), step=1)
nonfood_supply_qty_range = st.sidebar.slider("Gıda Dışı Temin Miktarı", min_value=1000, max_value=200000, value=(20000, 50000), step=1000)

st.sidebar.subheader("Araç ve Lojistik")
kamyon_count_range = st.sidebar.slider("Saatlik Kamyon Sayısı", min_value=0, max_value=10, value=(1, 4), step=1)
tir_count_range = st.sidebar.slider("Saatlik Tır Sayısı", min_value=0, max_value=6, value=(1, 3), step=1)
speed_range = st.sidebar.slider("Araç Hızı (km/saat)", min_value=30, max_value=110, value=(60, 80), step=1)
accident_prob_range = st.sidebar.slider("Araç Kaza/Arıza Oranı (%)", min_value=0.0, max_value=5.0, value=(1.0, 3.0), step=0.1)

st.sidebar.subheader("Tesis Arıza/Bakım")
breakdown_int_range = st.sidebar.slider("Duruş Sıklığı (Saat)", min_value=0, max_value=24, value=(8, 12), step=1)
breakdown_dur_range = st.sidebar.slider("Duruş Süresi (Dakika)", min_value=15, max_value=120, value=(30, 60), step=5)

st.sidebar.markdown("---")
st.sidebar.subheader("Simülasyon Ayarları")
num_runs = st.sidebar.slider("Simülasyon Koşu Sayısı", min_value=10, max_value=100, value=10, step=1)

# Başlığın dinamik hale getirilmesi
st.title(f"Migros Yardım Kolisi Operasyonu: Monte Carlo Simülasyon Analizi")
st.markdown(f"Bu uygulama, belirlenen parametre aralıklarına göre sistemi **{num_runs} kez** çalıştırarak süreçteki istatistiksel varyansları ve performans metriklerini analiz eder.")

if st.sidebar.button(f"Başlat", type="primary"):
    target_boxes = int(random.uniform(target_boxes_range[0], target_boxes_range[1]))
    distance = random.uniform(distance_range[0], distance_range[1])
    
    with st.spinner(f"Senaryo ({target_boxes:,} koli, {distance:.0f} km) için {num_runs} replikasyon hesaplanıyor..."):
        
        results = []
        sample_logs = []
        progress_bar = st.progress(0)
        
        # Olay tablosunun alınacağı simülasyon indeksi (en fazla 4. indeks veya toplam koşunun sonuncusu)
        sample_sim_index = min(4, num_runs - 1)
        
        for i in range(num_runs):
            is_sample_sim = (i == sample_sim_index)
            
            sim = AidSimulation(
                target_boxes=target_boxes, distance=distance, prod_range=prod_capacity_range,
                food_time_range=food_supply_time_range, food_qty_range=food_supply_qty_range,
                nonfood_time_range=nonfood_supply_time_range, nonfood_qty_range=nonfood_supply_qty_range,
                kamyon_range=kamyon_count_range, tir_range=tir_count_range, speed_range=speed_range,
                breakdown_dur_range=breakdown_dur_range, breakdown_int_range=breakdown_int_range,
                accident_prob_range=accident_prob_range,
                enable_logging=is_sample_sim
            )
            
            logs, total_time, accidents, maintenance_time = sim.run()
            
            if is_sample_sim:
                sample_logs = logs
                
            results.append({
                "Replikasyon": i + 1,
                "Toplam Tamamlanma Süresi (Saat)": total_time,
                "Kaza Yapan Araç Sayısı": accidents,
                "Toplam Tesis Duruş Süresi (Saat)": maintenance_time
            })
            progress_bar.progress((i + 1) / num_runs)
            
        df_results = pd.DataFrame(results)
        progress_bar.empty()
        
        # ---------------------------------------------------------
        # İSTATİSTİKSEL HESAPLAMALAR VE ÇIKARIM
        # ---------------------------------------------------------
        mean_time = df_results["Toplam Tamamlanma Süresi (Saat)"].mean()
        
        if num_runs > 1:
            std_time = df_results["Toplam Tamamlanma Süresi (Saat)"].std()
            margin_of_error = 1.96 * (std_time / np.sqrt(num_runs))
            lower_bound = mean_time - margin_of_error
            upper_bound = mean_time + margin_of_error
            std_text = f"standart sapması **{std_time:.1f} saat** olarak ölçülmüştür."
            ci_text = f"**%95 güven seviyesinde**, bu lojistik operasyonunun toplam tamamlanma süresinin **{lower_bound:.1f} saat ile {upper_bound:.1f} saat** arasında gerçekleşeceği öngörülmektedir."
        else:
            std_time = 0.0
            lower_bound = mean_time
            upper_bound = mean_time
            std_text = "tek bir simülasyon çalıştırıldığı için standart sapma hesaplanmamıştır."
            ci_text = f"bu lojistik operasyonunun toplam tamamlanma süresinin **{mean_time:.1f} saat** olarak gerçekleştiği gözlemlenmiştir."
        
        st.success(
            f"### Analiz Özeti ve İstatistiksel Çıkarım\n\n"
            f"**Sabit Senaryo:** {distance:.0f} km uzaklıktaki hedefe tam {target_boxes:,} adet kolinin teslim edilmesi.\n\n"
            f"**Çıkarım:** Seçilen model parametrelerine (kaza oranı: {accident_prob_range[0]}-{accident_prob_range[1]}%, "
            f"hız varyansı: {speed_range[0]}-{speed_range[1]} km/s, vb.) göre gerçekleştirilen {num_runs} bağımsız simülasyon sonucunda; "
            f"{ci_text}\n\n"
            f"Sistemin ortalama tamamlanma süresi **{mean_time:.1f} saat** (yaklaşık {mean_time/24:.1f} gün) olup, {std_text}"
        )
        
        # ---------------------------------------------------------
        # GÖRSELLEŞTİRME VE GRAFİKLER
        # ---------------------------------------------------------
        st.write("---")
        st.header("Dağılım ve Korelasyon Analizleri")
        
        col1, col2 = st.columns(2)
        with col1:
            fig_hist = px.histogram(
                df_results, x="Toplam Tamamlanma Süresi (Saat)", nbins=20, 
                title="Tamamlanma Sürelerinin Frekans Dağılımı",
                color_discrete_sequence=['#3366CC'], marginal="box"
            )
            fig_hist.update_layout(yaxis_title="Tekrar (Replikasyon) Sayısı")
            st.plotly_chart(fig_hist, use_container_width=True)
            
        with col2:
            scatter_trendline = "ols" if num_runs > 2 else None
            fig_scatter1 = px.scatter(
                df_results, x="Toplam Tesis Duruş Süresi (Saat)", y="Toplam Tamamlanma Süresi (Saat)",
                title="Üretim Hattı Duruşlarının Toplam Süreye Etkisi",
                trendline=scatter_trendline, color="Kaza Yapan Araç Sayısı", color_continuous_scale=px.colors.sequential.OrRd
            )
            st.plotly_chart(fig_scatter1, use_container_width=True)
            
        col3, col4 = st.columns(2)
        with col3:
            fig_box = px.box(
                df_results, y="Kaza Yapan Araç Sayısı", 
                title="Simülasyon Başına Araç Kaza/İptal Dağılımı",
                color_discrete_sequence=['#DC3912']
            )
            st.plotly_chart(fig_box, use_container_width=True)
            
        with col4:
            fig_line = px.line(
                df_results, x="Replikasyon", y="Toplam Tamamlanma Süresi (Saat)",
                title=f"{num_runs} Farklı Senaryo Tekrarındaki Süre Dalgalanmaları"
            )
            fig_line.add_hline(y=mean_time, line_dash="dash", line_color="green", annotation_text="Ortalama")
            st.plotly_chart(fig_line, use_container_width=True)

        with st.expander(f"Ham Sonuç Verilerini Görüntüle ({num_runs} Replikasyon)"):
            st.dataframe(df_results, use_container_width=True)
            
        # ---------------------------------------------------------
        # ÖRNEK OLAY TABLOSU
        # ---------------------------------------------------------
        st.write("---")
        st.subheader(f"Örnek olay tablosu:")
        if sample_logs:
            df_sample_logs = pd.DataFrame(sample_logs)
            st.dataframe(df_sample_logs, use_container_width=True)
        else:
            st.info("Bu iterasyon için olay günlüğü bulunamadı.")