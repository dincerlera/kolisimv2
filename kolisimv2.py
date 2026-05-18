import streamlit as st
import simpy
import random
import pandas as pd

# ---------------------------------------------------------
# SİMÜLASYON SINIFI VE FONKSİYONLARI
# ---------------------------------------------------------
class AidSimulation:
    def __init__(self, target_boxes, distance, prod_range, 
                 food_time_range, food_qty_range, 
                 nonfood_time_range, nonfood_qty_range,
                 kamyon_range, tir_range, speed_range,
                 breakdown_dur_range, breakdown_int_range, accident_prob_range):
        
        self.env = simpy.Environment()
        
        # Gıda ve Gıda Dışı içerikler ayrı modelleniyor
        self.food_materials = simpy.Container(self.env, init=0, capacity=float('inf'))
        self.nonfood_materials = simpy.Container(self.env, init=0, capacity=float('inf'))
        self.finished_goods = simpy.Container(self.env, init=0, capacity=float('inf'))
        
        # Kullanıcıdan alınan uniform dağılım sınırları
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
        
        # Verilen aralıktan uniform dağılımla simülasyonun kaza/arıza oranı belirlenir
        self.accident_rate = random.uniform(accident_prob_range[0], accident_prob_range[1]) / 100.0
        
        # Simülasyon takip değişkenleri
        self.total_shipped = 0
        self.total_delivered = 0
        self.logs = []
        self.delivery_times = []
        self.completion_event = self.env.event()
        self.is_under_maintenance = False

    def log_event(self, time, event_type, details):
        """Gerçekleşen olayları ön yüzde göstermek için kaydeder."""
        self.logs.append({
            "Saat": round(time, 2),
            "Olay": event_type,
            "Detay": details,
            "Ulaşan Toplam Koli": self.total_delivered
        })

    def food_supplier_process(self):
        """Gıda içeriklerinin tesise gelişini simüle eder."""
        initial_supply = int(random.uniform(*self.food_qty_range))
        yield self.food_materials.put(initial_supply)
        self.log_event(self.env.now, "İlk Tedarik (Gıda)", f"{initial_supply} adet gıda içeriği stoka girdi.")

        while self.total_shipped < self.target_boxes:
            supply_interval = random.uniform(*self.food_time_range)
            yield self.env.timeout(supply_interval)
            
            supply_qty = int(random.uniform(*self.food_qty_range))
            yield self.food_materials.put(supply_qty)
            self.log_event(self.env.now, "Tedarik (Gıda)", f"{supply_qty} adet gıda içeriği stoka girdi. (Mevcut: {self.food_materials.level})")

    def nonfood_supplier_process(self):
        """Gıda dışı içeriklerinin tesise gelişini simüle eder."""
        initial_supply = int(random.uniform(*self.nonfood_qty_range))
        yield self.nonfood_materials.put(initial_supply)
        self.log_event(self.env.now, "İlk Tedarik (Gıda Dışı)", f"{initial_supply} adet gıda dışı içerik stoka girdi.")

        while self.total_shipped < self.target_boxes:
            supply_interval = random.uniform(*self.nonfood_time_range)
            yield self.env.timeout(supply_interval)
            
            supply_qty = int(random.uniform(*self.nonfood_qty_range))
            yield self.nonfood_materials.put(supply_qty)
            self.log_event(self.env.now, "Tedarik (Gıda Dışı)", f"{supply_qty} adet gıda dışı içerik stoka girdi. (Mevcut: {self.nonfood_materials.level})")

    def maintenance_process(self):
        """Belirlenen aralıklarda ve sürelerde üretim sürecini durduran arıza/bakım süreci."""
        while self.total_shipped < self.target_boxes:
            interval = random.uniform(*self.breakdown_int_range)
            if interval == 0:
                interval = 0.1 # Sonsuz döngüyü önlemek için minimum güvenlik payı
            yield self.env.timeout(interval)
            
            duration_mins = random.uniform(*self.breakdown_dur_range)
            duration_hours = duration_mins / 60.0
            
            self.is_under_maintenance = True
            self.log_event(self.env.now, "Üretim Duruşu", f"Arıza/Bakım başladı. Üretim {duration_mins:.0f} dakika durduruldu.")
            
            yield self.env.timeout(duration_hours)
            
            self.is_under_maintenance = False
            self.log_event(self.env.now, "Üretim Başladı", "Arıza/Bakım tamamlandı, üretim devam ediyor.")

    def production_process(self):
        """1 gıda ve 1 gıda dışı içerik kullanarak koli üreten süreci simüle eder."""
        while self.total_shipped < self.target_boxes:
            yield self.env.timeout(1)
            
            if self.is_under_maintenance:
                continue  # Arıza/bakım süresince üretim yapılmaz
                
            current_capacity = int(random.uniform(*self.prod_range))
            
            # 1 koli için 1 gıda ve 1 gıda dışı içerik gereklidir
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
                    self.log_event(self.env.now, "Üretim", f"{production_amount} koli üretildi. (Depodaki koli: {self.finished_goods.level})")

    def logistics_process(self):
        """Üretilen kolilerin Tır ve Kamyonlara yüklenip yola çıkmasını simüle eder."""
        while self.total_shipped < self.target_boxes:
            yield self.env.timeout(1)
            
            remaining_to_ship = self.target_boxes - self.total_shipped
            if remaining_to_ship <= 0:
                break
                
            tir_count = int(random.uniform(*self.tir_range))
            kamyon_count = int(random.uniform(*self.kamyon_range))
            
            # Tır Gönderimleri (Kapasite 1500)
            for _ in range(tir_count):
                if self.finished_goods.level > 0 and self.total_shipped < self.target_boxes:
                    amount_to_load = min(1500, self.target_boxes - self.total_shipped, self.finished_goods.level)
                    if amount_to_load > 0:
                        yield self.finished_goods.get(amount_to_load)
                        self.total_shipped += amount_to_load
                        self.env.process(self.vehicle_delivery(amount_to_load, "Tır"))

            # Kamyon Gönderimleri (Kapasite 750)
            for _ in range(kamyon_count):
                if self.finished_goods.level > 0 and self.total_shipped < self.target_boxes:
                    amount_to_load = min(750, self.target_boxes - self.total_shipped, self.finished_goods.level)
                    if amount_to_load > 0:
                        yield self.finished_goods.get(amount_to_load)
                        self.total_shipped += amount_to_load
                        self.env.process(self.vehicle_delivery(amount_to_load, "Kamyon"))

    def vehicle_delivery(self, amount, vehicle_type):
        """Araçların (Tır/Kamyon) hedef noktaya seyahatini, hızlarını ve olası kazaları simüle eder."""
        # Araç hızı uniform dağılımla belirlenir
        speed = random.uniform(*self.speed_range)
        travel_time = self.distance / speed
        
        self.log_event(self.env.now, "Sevkiyat Çıkışı", f"{amount} koli yüklü {vehicle_type} yola çıktı. (Hız: {speed:.1f} km/s)")
        
        # Kaza durumu kontrolü
        if random.random() < self.accident_rate:
            # Araç kaza yapar, teslimat gerçekleşmez (Örnek olarak yolun yarısında kaza yapmış olsun)
            yield self.env.timeout(travel_time / 2)
            self.log_event(self.env.now, "Kaza/Arıza - Teslimat İptali", f"{vehicle_type} kaza yaptı! {amount} koli teslim edilemedi.")
            
            # İhtiyacın kapanması için sevk edilen miktar sistemden geri çekilir, tekrar üretim/sevk tetiklenir
            self.total_shipped -= amount
        else:
            # Yolculuk süresi kadar bekleme
            yield self.env.timeout(travel_time)
            
            # Hedefe varış
            self.total_delivered += amount
            self.delivery_times.append({"Saat": self.env.now, "Teslim Edilen": self.total_delivered})
            self.log_event(self.env.now, "Teslimat", f"1 {vehicle_type} hedefe ulaştı. Getirdiği koli: {amount}")
            
            # Tüm hedefe ulaşıldıysa simülasyonu bitir
            if self.total_delivered >= self.target_boxes:
                if not self.completion_event.triggered:
                    self.completion_event.succeed()

    def run(self):
        """Tüm süreçleri başlatır ve simülasyonu çalıştırır."""
        self.env.process(self.food_supplier_process())
        self.env.process(self.nonfood_supplier_process())
        self.env.process(self.maintenance_process())
        self.env.process(self.production_process())
        self.env.process(self.logistics_process())
        
        self.env.run(until=self.completion_event)
        return self.logs, self.delivery_times, self.env.now

# ---------------------------------------------------------
# STREAMLIT ÖN YÜZ (ARAYÜZ)
# ---------------------------------------------------------
st.set_page_config(page_title="Yardım Kolisi Lojistik Simülasyonu", layout="wide")
st.title("Yardım Kolisi Üretim ve Lojistik Simülasyonu")
st.markdown("Bu uygulama, belirlenen senaryo ve dağılımlara göre yardım kolilerinin tedarik, üretim ve teslimat süreçlerini simüle eder.")

# Sidebar (Sol Panel) - Girdiler
st.sidebar.header("Uniform Dağılım Parametreleri")

target_boxes_range = st.sidebar.slider(
    "Gereken Yardım Kolisi Sayısı",
    min_value=10000, max_value=200000, value=(50000, 100000), step=1000
)

distance_range = st.sidebar.slider(
    "Mesafe (km)",
    min_value=50, max_value=750, value=(200, 400), step=10
)

prod_capacity_range = st.sidebar.slider(
    "Saatlik Üretim Kapasitesi",
    min_value=350, max_value=1500, value=(800, 1200), step=50
)

# Tedarik Parametreleri - İkiye Bölündü
st.sidebar.subheader("Gıda İçerik Tedariki")
food_supply_time_range = st.sidebar.slider(
    "Gıda İçerik Temin Süresi (Saat)",
    min_value=1, max_value=72, value=(24, 48), step=1
)

food_supply_qty_range = st.sidebar.slider(
    "Gıda İçeriği Temin Miktarı",
    min_value=1000, max_value=200000, value=(20000, 50000), step=1000
)

st.sidebar.subheader("Gıda Dışı İçerik Tedariki")
nonfood_supply_time_range = st.sidebar.slider(
    "Gıda Dışı İçerik Temin Süresi (Saat)",
    min_value=1, max_value=72, value=(24, 48), step=1
)

nonfood_supply_qty_range = st.sidebar.slider(
    "Gıda Dışı İçeriği Temin Miktarı",
    min_value=1000, max_value=200000, value=(20000, 50000), step=1000
)

# Araç ve Lojistik Parametreleri
st.sidebar.subheader("Araç ve Lojistik Parametreleri")
kamyon_count_range = st.sidebar.slider(
    "Saatlik Kamyon Sayısı",
    min_value=0, max_value=10, value=(1, 4), step=1
)

tir_count_range = st.sidebar.slider(
    "Saatlik Tır Sayısı",
    min_value=0, max_value=6, value=(1, 3), step=1
)

speed_range = st.sidebar.slider(
    "Araç Hızı (km/saat)",
    min_value=30, max_value=110, value=(60, 80), step=1
)

accident_prob_range = st.sidebar.slider(
    "Araç Kaza/Arıza Oranı (%)",
    min_value=0.0, max_value=5.0, value=(1.0, 3.0), step=0.1
)

# Üretim Duruş (Arıza/Bakım) Parametreleri
st.sidebar.subheader("Tesis Arıza/Bakım Parametreleri")
breakdown_int_range = st.sidebar.slider(
    "Arıza-Bakım Kaynaklı Duruş Sıklığı (Saat)",
    min_value=0, max_value=24, value=(8, 12), step=1
)

breakdown_dur_range = st.sidebar.slider(
    "Arıza-Bakım Süresi (Dakika)",
    min_value=15, max_value=120, value=(30, 60), step=5
)

if st.sidebar.button("Simülasyonu Çalıştır", type="primary"):
    with st.spinner("Simülasyon yürütülüyor..."):
        
        target_boxes = int(random.uniform(target_boxes_range[0], target_boxes_range[1]))
        distance = random.uniform(distance_range[0], distance_range[1])
        
        sim = AidSimulation(
            target_boxes=target_boxes,
            distance=distance,
            prod_range=prod_capacity_range,
            food_time_range=food_supply_time_range,
            food_qty_range=food_supply_qty_range,
            nonfood_time_range=nonfood_supply_time_range,
            nonfood_qty_range=nonfood_supply_qty_range,
            kamyon_range=kamyon_count_range,
            tir_range=tir_count_range,
            speed_range=speed_range,
            breakdown_dur_range=breakdown_dur_range,
            breakdown_int_range=breakdown_int_range,
            accident_prob_range=accident_prob_range
        )
        
        logs, delivery_times, total_time = sim.run()
        
        df_logs = pd.DataFrame(logs)
        df_deliveries = pd.DataFrame(delivery_times)
        
        # ---------------------------------------------------------
        # SONUÇLARIN GÖSTERİMİ
        # ---------------------------------------------------------
        st.success(f"Simülasyon başarıyla tamamlandı! Toplam Süre: {total_time:.2f} Saat (Yaklaşık {total_time/24:.1f} Gün)")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Hedeflenen Koli", f"{target_boxes:,}")
        col2.metric("Mesafe", f"{distance:.0f} km")
        col3.metric("Ulaşan Toplam Koli", f"{sim.total_delivered:,}")

        st.subheader("Teslimat İlerleme Grafiği")
        if not df_deliveries.empty:
            df_chart = df_deliveries.set_index("Saat")
            st.line_chart(df_chart["Teslim Edilen"])
        else:
            st.info("Gösterilecek teslimat verisi bulunamadı.")

        st.subheader("Simülasyon Olay Kayıtları (Tablo)")
        st.dataframe(df_logs, use_container_width=True)