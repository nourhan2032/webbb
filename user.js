let map;
let userMarker; 

function initMap() {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const userLocation = { lat: position.coords.latitude, lng: position.coords.longitude };

                map = new google.maps.Map(document.getElementById("map"), {
                    center: userLocation, 
                    zoom: 14, 
                    disableDefaultUI: true 
                });

                userMarker = new google.maps.Marker({
                    position: userLocation,
                    map: map,
                    icon: {
                        path: google.maps.SymbolPath.CIRCLE,
                        fillColor: '#4285F4',
                        fillOpacity: 1,
                        strokeColor: 'white',
                        strokeWeight: 2,
                        scale: 7
                    }
                });

                addSmartGarages(userLocation); 
            },
            () => { alert("Please allow location access to display your position on the map."); }
        );
    }
}

// 🎯 الدالة الذكية والمطابقة بالمللي لـ navigation.js من حيث الحسابات والـ API والترتيب
async function addSmartGarages(userLocation) {
    console.log("📡 Live Data from Server:", liveGaragesData); // للـ Debugging

    if (typeof liveGaragesData === 'undefined' || !liveGaragesData) return;

    const bounds = new google.maps.LatLngBounds();
    const cards = Array.from(document.querySelectorAll('.garage-card')); 
    const garagesContainer = document.querySelector('.nearest-garages');

    // 1. تصفية واستخراج الجراجات اللي ليها إحداثيات سليمة
    let garagesList = liveGaragesData.map(garage => {
        const lat = parseFloat(garage.lat);
        const lng = parseFloat(garage.lng);
        return { ...garage, lat, lng };
    }).filter(g => !isNaN(g.lat) && !isNaN(g.lng) && (g.lat !== 0 || g.lng !== 0));

    // 2. نفس معادلة الزحمة (Traffic Simulation) اللي في navigation.js بالظبط
    const currentHour = new Date().getHours();
    let trafficMultiplier = 1.3; // زحمة عادية في مصر
    if ((currentHour >= 8 && currentHour <= 10) || (currentHour >= 14 && currentHour <= 19)) {
        trafficMultiplier = 1.8; // وقت الذروة
    }

    // 3. سحب البيانات الحقيقية من الشوارع لكل الجراجات بالتوازي (صورة طبق الأصل من الـ Navigation)
    const fetchPromises = garagesList.map(async (garage) => {
        let routedDistance = Infinity;
        let estimatedMinutes = Infinity;
        let timeFormatted = "-- mins";
        let distanceFormatted = "-- km";

        try {
            // نفس الـ URL المستخدم جوه الـ Navigation بالظبط
            const url = `https://router.project-osrm.org/route/v1/driving/${userLocation.lng},${userLocation.lat};${garage.lng},${garage.lat}?overview=false`;
            const response = await fetch(url);
            const data = await response.json();

            if (data.routes && data.routes.length > 0) {
                routedDistance = data.routes[0].distance; // بالمتر (على الشارع)
                const baseDuration = data.routes[0].duration; // بالثانية (طريق فاضي)

                const realisticSeconds = baseDuration * trafficMultiplier;
                estimatedMinutes = Math.ceil(realisticSeconds / 60);

                // ==========================================
                // 💡 تنسيق الوقت المتطابق بالمللي (ساعات ودقائق)
                // ==========================================
                if (estimatedMinutes <= 1) {
                    timeFormatted = "Less than a min";
                } else if (estimatedMinutes < 60) {
                    timeFormatted = `${estimatedMinutes} mins`;
                } else {
                    const hours = Math.floor(estimatedMinutes / 60);
                    const mins = estimatedMinutes % 60;
                    timeFormatted = mins > 0 ? `${hours} h ${mins} mins` : `${hours} h`;
                }

                // ==========================================
                // 💡 تنسيق المسافة المتطابق بالمللي (متر وكيلومتر)
                // ==========================================
                if (routedDistance < 1000) {
                    distanceFormatted = `${Math.round(routedDistance)} m`;
                } else {
                    const km = (routedDistance / 1000).toFixed(1);
                    distanceFormatted = `${km} km`;
                }
            }
        } catch (err) {
            console.error("⚠️ ETA Fetch error for " + garage.name + ":", err);
            // نظام احتياطي (Fallback) في حالة سقوط السيرفر باستخدام الهيفرسين
            routedDistance = calculateDistance(userLocation.lat, userLocation.lng, garage.lat, garage.lng);
            estimatedMinutes = Math.ceil((routedDistance / 1000) * 2 * trafficMultiplier); 
            timeFormatted = `${estimatedMinutes} mins`;
            distanceFormatted = `${(routedDistance / 1000).toFixed(1)} km`;
        }

        return { 
            ...garage, 
            routedDistance, 
            estimatedMinutes, 
            timeFormatted, 
            distanceFormatted 
        };
    });

    // الانتظار حتى اكتمال جلب البيانات لكل الجراجات
    let garagesWithRealTime = await Promise.all(fetchPromises);

    // ==============================================================
    // 💡 4. الترتيب الثنائي الصارم (الأقل وقتاً أولاً، ثم الأقل مسافة)
    // ==============================================================
    garagesWithRealTime.sort((a, b) => {
        if (a.estimatedMinutes === b.estimatedMinutes) {
            return a.routedDistance - b.routedDistance; // لو الوقت متساوي، يرتب بالأقرب مسافة
        }
        return a.estimatedMinutes - b.estimatedMinutes; // الترتيب الأساسي بالوقت الأقل
    });

    // 5. قطف أقرب 3 جراجات فقط بناءً على الترتيب الجديد
    const top3Garages = garagesWithRealTime.slice(0, 4);

    // 6. تحديث الكروت وتطبيق الفلترة والاختفاء في الـ HTML
    cards.forEach(card => {
        const titleElement = card.querySelector('h4');
        if (titleElement) {
            const htmlName = titleElement.innerText.trim().toLowerCase();
            
            // البحث عن الجراج المطابق في القائمة الحية لأقرب 3 جراجات
            const matchingGarage = top3Garages.find(g => 
                htmlName.includes(g.name.trim().toLowerCase()) || 
                g.name.trim().toLowerCase().includes(htmlName)
            );

            if (matchingGarage) {
                const distanceElement = card.querySelector('p');
                if (distanceElement) {
                    // إظهار الوقت والمسافة بتنسيق فخم ومتطابق مع البار السفلي للملاحة
                    distanceElement.innerHTML = `
                        <i class="fa-solid fa-clock" style="color: #00c2b8;"></i> <span style="font-weight: bold; color: white;">${matchingGarage.timeFormatted}</span> 
                        <span style="color: #334155; margin: 0 5px;">|</span> 
                        <i class="fa-solid fa-location-dot" style="color: #94a3b8;"></i> ${matchingGarage.distanceFormatted}`;
                }
                card.style.display = 'block'; // إظهار الكارت
                card.dataset.sortOrder = top3Garages.indexOf(matchingGarage); // حفظ الترتيب الصحيح
            } else {
                card.style.display = 'none'; // إخفاء الجراج لو مش من التوب 3 القريبين
            }
        }
    });

    // 7. إعادة ترتيب الكروت داخل الـ Container في الصفحة لتعكس الترتيب الثنائي بدقة
    const visibleCards = Array.from(document.querySelectorAll('.garage-card')).filter(c => c.style.display !== 'none');
    visibleCards.sort((a, b) => parseInt(a.dataset.sortOrder) - parseInt(b.dataset.sortOrder));
    visibleCards.forEach(card => garagesContainer.appendChild(card));

    // 8. إسقاط الدبابيس (Markers) لأقرب 3 جراجات فقط على الخريطة
    top3Garages.forEach(garage => {
        const garageLocation = { lat: garage.lat, lng: garage.lng };
        bounds.extend(garageLocation);

        const marker = new google.maps.Marker({
            position: garageLocation, 
            map: map, 
            title: garage.name
        });

        const statusClass = garage.free_spots > 0 ? "free-slots" : "busy-slots";
        const statusText = garage.free_spots > 0 ? `${garage.free_spots} spots available` : "Fully occupied";

        const infoContent = `
            <div class="info-box" style="color: #0f172a; padding: 5px;">
                <h4 style="margin: 0 0 5px 0;">${garage.name}</h4>
                <p style="margin: 0 0 5px 0; font-size: 0.9rem;">Capacity: ${garage.total_spots} cars</p>
                <p style="margin: 0; font-weight: bold;" class="${statusClass}">${statusText}</p>
            </div>
        `;

        const infowindow = new google.maps.InfoWindow({ content: infoContent });
        marker.addListener("click", () => { infowindow.open(map, marker); });
    });

    // 9. تركيز كاميرا الخريطة لتشمل المستخدم وأقرب جراجات بحجم مثالي
    if (!bounds.isEmpty()) {
        bounds.extend(userLocation); 
        map.fitBounds(bounds);
    }
}

function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371000; 
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))); 
}


/* =========================================
   Booking Modal Logic & Dynamic Pricing
========================================= */

let currentPrices = { standard: 0, vip: 0, special_needs: 0 };

async function fetchDynamicPrices(garageId) {
    try {
        document.getElementById('price-standard').innerText = '...';
        document.getElementById('price-vip').innerText = '...';
        document.getElementById('price-special').innerText = '...';
        if(document.getElementById('finalPriceDisplay')) document.getElementById('finalPriceDisplay').innerText = '...';

        const response = await fetch(`/api/get_garage_prices?garage_id=${garageId}`);
        const data = await response.json();

        if (data.status === 'success') {
            currentPrices.standard = data.prices.standard;
            currentPrices.vip = data.prices.vip;
            currentPrices.special_needs = data.prices.special_needs;

            document.getElementById('price-standard').innerText = `${currentPrices.standard} EGP/h`;
            document.getElementById('price-vip').innerText = `${currentPrices.vip} EGP/h`;
            document.getElementById('price-special').innerText = `${currentPrices.special_needs} EGP/h`;

            calculatePrice();
        } else {
            console.error("Backend Error:", data.message);
            alert("Error loading prices: " + data.message);
        }
    } catch (error) {
        console.error("Network error:", error);
    }
}

const bookingModal = document.getElementById('bookingModal');
const closeBookingBtn = document.getElementById('closeBookingBtn');
const openBookingBtns = document.querySelectorAll('.open-booking-btn'); 

const minusBtn = document.getElementById('minusHour');
const plusBtn = document.getElementById('plusHour');
const durationDisplay = document.getElementById('durationDisplay');
const spotRadios = document.querySelectorAll('input[name="spotType"]');
const finalPriceDisplay = document.getElementById('finalPriceDisplay');
const bookingForm = document.getElementById('bookingForm');
const vehicleSelect = document.getElementById('vehicleSelect'); 

let currentHours = 1;
let currentGarageId = 1;

async function fetchUserVehicles() {
    if (!vehicleSelect) return;
    
    vehicleSelect.innerHTML = '<option disabled selected>Loading your vehicles...</option>';
    
    try {
        const response = await fetch('/api/get_user_cars');
        const data = await response.json();

        if (data.status === 'success') {
            vehicleSelect.innerHTML = ''; 

            if (data.cars.length === 0) {
                vehicleSelect.innerHTML = '<option disabled selected>No vehicles found. Add one first.</option>';
                return;
            }

            data.cars.forEach((car, index) => {
                const option = document.createElement('option');
                option.value = car.id; 
                option.text = `🚗 Plate: ${car.plate_no}`; 
                if (index === 0) option.selected = true; 
                vehicleSelect.appendChild(option);
            });
        } else {
            vehicleSelect.innerHTML = '<option disabled selected>Error loading vehicles</option>';
        }
    } catch (error) {
        vehicleSelect.innerHTML = '<option disabled selected>Network error</option>';
    }
}

function initializeModalData() {
    document.getElementById('price-standard').innerText = '...';
    document.getElementById('price-vip').innerText = '...';
    document.getElementById('price-special').innerText = '...';
    if(finalPriceDisplay) finalPriceDisplay.innerText = '...';

    currentHours = 1;
    if(durationDisplay) durationDisplay.innerText = currentHours;

    // =========================================================
    // 💡 التعديل هنا: تصفير السلوت وإرجاع زرار الاختيار لشكله الطبيعي
    // =========================================================
    userChosenSlot = null; // تفريغ المتغير اللي بيتبعت للداتا بيز
    if(chooseSlotBtn) chooseSlotBtn.style.display = 'block'; // إظهار زرار "Choose Your Slot"
    if(selectedSlotDisplay) selectedSlotDisplay.style.display = 'none'; // إخفاء المربع اللي فيه السلوت القديم
}

if (openBookingBtns.length > 0) {
    openBookingBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            if (btn.hasAttribute('disabled')) return;

            const card = btn.closest('.garage-card');
            const garageName = card.querySelector('h4').innerText;
            localStorage.setItem('selectedGarageName', garageName);

            const modalGarageNameEl = document.getElementById('modalGarageName');
            if (modalGarageNameEl) {
                modalGarageNameEl.innerText = garageName;
            }
            
            initializeModalData();

            let garageId = 1; 
            if(garageName.includes("Festival")) garageId = 1;
            else if(garageName.includes("Citystars")) garageId = 2;
            else if(garageName.includes("Arabia")) garageId = 3;
            else if(garageName.includes("Egypt")) garageId = 4;
            else if(garageName.includes("Almaza")) garageId = 5;
            else if(garageName.includes("Downtown")) garageId = 6;

            currentGarageId = garageId; 

            fetchUserVehicles(); 
            fetchDynamicPrices(garageId); 
            
            if(bookingModal) bookingModal.classList.add('active');
        });
    });
}

if (closeBookingBtn) {
    closeBookingBtn.addEventListener('click', () => {
        if(bookingModal) bookingModal.classList.remove('active');
    });
}

function calculatePrice() {
    const checkedRadio = document.querySelector('input[name="spotType"]:checked');
    if(!checkedRadio || !finalPriceDisplay) return;

    const selectedSpot = checkedRadio.value;
    const pricePerHour = currentPrices[selectedSpot]; 
    
    if (pricePerHour > 0) {
        let total = Math.round(pricePerHour * currentHours);
        finalPriceDisplay.innerText = total;
    }
}

if (plusBtn) {
    plusBtn.addEventListener('click', () => {
        if (currentHours < 24) {
            currentHours++;
            durationDisplay.innerText = currentHours;
            calculatePrice();
        }
    });
}
if (minusBtn) {
    minusBtn.addEventListener('click', () => {
        if (currentHours > 1) {
            currentHours--;
            durationDisplay.innerText = currentHours;
            calculatePrice();
        }
    });
}

if (spotRadios.length > 0) {
    spotRadios.forEach(radio => {
        radio.addEventListener('change', calculatePrice);
    });
}

const parkingSlotsData = {
    vip: [ 
        { id: 'V-01', status: 'available' }, 
        { id: 'V-02', status: 'occupied' },
        { id: 'V-03', status: 'available' }
    ],
    special_needs: [ 
        { id: 'S-01', status: 'available' }, 
        { id: 'S-02', status: 'occupied' } 
    ],
    standard: [ 
        { id: 'A-01', status: 'occupied' }, 
        { id: 'A-02', status: 'available' }, 
        { id: 'A-03', status: 'available' }, 
        { id: 'A-04', status: 'occupied' },
        { id: 'A-05', status: 'available' },
        { id: 'A-06', status: 'occupied' }
    ]
};

const chooseSlotBtn = document.getElementById('chooseSlotBtn');
const slotDashboardModal = document.getElementById('slotDashboardModal');
const closeSlotDashboardBtn = document.getElementById('closeSlotDashboardBtn');
const selectedSlotDisplay = document.getElementById('selectedSlotDisplay');
const chosenSlotText = document.getElementById('chosenSlotText');
const changeSlotBtn = document.getElementById('changeSlotBtn');

let userChosenSlot = null; 

function renderParkingLayout() {
    const checkedRadio = document.querySelector('input[name="spotType"]:checked');
    if(!checkedRadio) return;
    const currentCategory = checkedRadio.value; 
    
    const renderZone = (gridId, categoryKey) => {
        const grid = document.getElementById(gridId);
        if(!grid) return;
        grid.innerHTML = ''; 
        
        parkingSlotsData[categoryKey].forEach(slot => {
            const isLocked = currentCategory !== categoryKey;
            const isAvailable = slot.status === 'available';
            
            let boxClass = 'slot-box-ui';
            let icon = 'fa-car';
            let statusText = '';

            if (isLocked) {
                boxClass += ' locked';
                icon = 'fa-lock';
                statusText = 'Locked';
            } else if (isAvailable) {
                boxClass += ' available';
                statusText = 'متاح';
            } else {
                boxClass += ' occupied';
                statusText = 'مشغول';
            }

            const clickAction = (!isLocked && isAvailable) ? `onclick="confirmSlotSelection('${slot.id}')"` : '';

            const boxHTML = `
                <div class="${boxClass}" ${clickAction}>
                    <i class="fa-solid ${icon}" style="font-size: 1.5rem;"></i>
                    <span class="slot-name-ui">${slot.id}</span>
                    <span class="status-badge">${statusText}</span>
                </div>
            `;
            grid.innerHTML += boxHTML;
        });
    };

    renderZone('vipSlotsGrid', 'vip');
    renderZone('accessibleSlotsGrid', 'special_needs');
    renderZone('standardSlotsGrid', 'standard');
}

// Update Choose Slot Button Click Listener
if(chooseSlotBtn) {
    chooseSlotBtn.addEventListener('click', () => {
        chooseSlotBtn.style.setProperty('border-color', '#00c2b8', 'important');
        chooseSlotBtn.style.setProperty('color', '#00c2b8', 'important');
        chooseSlotBtn.innerHTML = '<i class="fa-solid fa-map"></i> Choose Your Slot';
        
        // 🚀 Call the live sync function instead of calling renderParkingLayout directly
        fetchAndRenderLiveSlots(currentGarageId);
        
        if(slotDashboardModal) slotDashboardModal.classList.add('active');
    });
}

// Update Change Slot Button Click Listener
if(changeSlotBtn) {
    changeSlotBtn.addEventListener('click', () => {
        // 🚀 Call the live sync function here as well to renew availability states
        fetchAndRenderLiveSlots(currentGarageId);
        
        if(slotDashboardModal) slotDashboardModal.classList.add('active');
    });
}

if(closeSlotDashboardBtn) {
    closeSlotDashboardBtn.addEventListener('click', () => {
        if(slotDashboardModal) slotDashboardModal.classList.remove('active');
    });
}

window.confirmSlotSelection = function(slotId) {
    userChosenSlot = slotId; 
    if(slotDashboardModal) slotDashboardModal.classList.remove('active'); 
    
    if(chooseSlotBtn) chooseSlotBtn.style.display = 'none';
    if(selectedSlotDisplay) selectedSlotDisplay.style.display = 'flex';
    if(chosenSlotText) chosenSlotText.innerText = `Slot: ${slotId}`;
};

if (spotRadios.length > 0) {
    spotRadios.forEach(radio => {
        radio.addEventListener('change', () => {
            calculatePrice(); 
            userChosenSlot = null;
            if(chooseSlotBtn) chooseSlotBtn.style.display = 'block';
            if(selectedSlotDisplay) selectedSlotDisplay.style.display = 'none';
        });
    });
}

if (bookingForm) {
    bookingForm.addEventListener('submit', async (e) => {
        e.preventDefault(); 

        if (!userChosenSlot) {
            chooseSlotBtn.style.setProperty('border-color', '#ef4444', 'important');
            chooseSlotBtn.style.setProperty('color', '#ef4444', 'important');
            chooseSlotBtn.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> Please choose your slot first!';
            return; 
        }

        // =====================================================================
        // 💡 التعديل الجديد: التشيك الذكي على رصيد المحفظة قبل الحجز
        // =====================================================================
        
        // 1. هنسحب التكلفة الإجمالية اللي ظهرت لليوزر
        const finalPriceText = finalPriceDisplay.innerText;
        const requiredAmount = parseFloat(finalPriceText);

        // 2. هنسحب رصيد المحفظة من الهيدر فوق (وبنفلتره عشان لو مكتوب جنبه EGP)
        const balanceElement = document.querySelector('.wallet-badge strong');
        let currentBalance = 0;
        if (balanceElement) {
            // السطر ده بياخد الأرقام بس من النص (مثلاً "50.00 EGP" هيخليها 50.00)
            currentBalance = parseFloat(balanceElement.innerText.replace(/[^\d.-]/g, ''));
        }

        // 3. المقارنة الحاسمة
        if (currentBalance < requiredAmount) {
            alert(`عفواً، رصيد محفظتك الحالي (${currentBalance} EGP) لا يكفي.\nتحتاج إلى شحن المحفظة بـ ${requiredAmount} EGP على الأقل لإتمام الحجز.`);
            
            // توجيه تلقائي لصفحة المحفظة عشان يشحن
            window.location.href = 'wallet.html';
            return; // 🛑 بنوقف تنفيذ الكود هنا عشان ميبعتش حاجة للداتا بيز
        }
        // =====================================================================

        const carId = vehicleSelect.value; 
        const spotType = document.querySelector('input[name="spotType"]:checked').value; 
        const reservedHourPrice = currentPrices[spotType]; 

        if (reservedHourPrice === 0) {
            alert("Please wait for the dynamic prices to load securely.");
            return;
        }

        const submitBtn = document.querySelector('button[type="submit"]');
        const originalBtnText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
        submitBtn.disabled = true;

        try {
            const response = await fetch('/api/create_reservation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    car_id: carId,
                    spot_type: spotType,
                    hour_price: reservedHourPrice,
                    duration: currentHours,
                    garage_id: currentGarageId,
                    slot_name: userChosenSlot
                })
            });

            const result = await response.json();

            if (result.status === 'success') {
                const selectedVehicleText = vehicleSelect.options[vehicleSelect.selectedIndex].text.replace('🚗 Plate: ', ''); 
                
                // حفظ بيانات الفاتورة
                localStorage.setItem('bookingPrice', finalPriceText);
                localStorage.setItem('bookedVehicle', selectedVehicleText); 
                localStorage.setItem('bookedSlot', userChosenSlot); 
                
                // 💡 التعديل هنا: استخراج إحداثيات الجراج اللي اتحجز وحفظها للـ Navigation
                const targetGarage = liveGaragesData.find(g => g.garage_id === currentGarageId || g.name.includes(localStorage.getItem('selectedGarageName')));
                
                if (targetGarage) {
                    localStorage.setItem('navGarageName', targetGarage.name);
                    localStorage.setItem('navGarageLat', targetGarage.lat);
                    localStorage.setItem('navGarageLng', targetGarage.lng);
                }

                // توجيه لصفحة التذكرة
                window.location.href = 'payment.html';
            } else {
                alert("Database Error: " + result.message);
                submitBtn.innerHTML = originalBtnText;
                submitBtn.disabled = false;
            }
        } catch (error) {
            console.error("Network error:", error);
            alert("Network error while communicating with the server.");
            submitBtn.innerHTML = originalBtnText;
            submitBtn.disabled = false;
        }
    });
}

if(chooseSlotBtn) {
    chooseSlotBtn.addEventListener('click', () => {
        chooseSlotBtn.style.setProperty('border-color', '#00c2b8', 'important');
        chooseSlotBtn.style.setProperty('color', '#00c2b8', 'important');
        chooseSlotBtn.innerHTML = '<i class="fa-solid fa-map"></i> Choose Your Slot';
        
        renderParkingLayout();
        if(slotDashboardModal) slotDashboardModal.classList.add('active');
    });
}

/* ==========================================================================
   UI Components (Notifications, Avatar, Settings, Theme, Logout)
   معزولة تماماً في الأسفل لعدم التأثير على الكود الأساسي
   ========================================================================== */
document.addEventListener("DOMContentLoaded", () => {
    
    // 1. Theme Toggle
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        if (localStorage.getItem('theme') === 'light') {
            document.body.classList.add('light-mode');
            themeToggle.innerHTML = '<i class="fa-solid fa-sun"></i>';
        }
        themeToggle.addEventListener('click', () => {
            document.body.classList.toggle('light-mode');
            if (document.body.classList.contains('light-mode')) {
                localStorage.setItem('theme', 'light');
                themeToggle.innerHTML = '<i class="fa-solid fa-sun"></i>';
            } else {
                localStorage.setItem('theme', 'dark');
                themeToggle.innerHTML = '<i class="fa-solid fa-moon"></i>';
            }
        });
    }

    // 2. Profile Dropdown Menu
    const avatarMenuBtn = document.getElementById("avatarMenuBtn");
    const avatarDropdown = document.getElementById("avatarDropdown");

    if (avatarMenuBtn && avatarDropdown) {
        avatarMenuBtn.addEventListener("click", (e) => { 
            e.stopPropagation(); 
            avatarDropdown.classList.toggle("active"); 
        });
        window.addEventListener("click", (e) => {
            if (avatarDropdown.classList.contains("active")) {
                if (!avatarDropdown.contains(e.target) && !avatarMenuBtn.contains(e.target)) {
                    avatarDropdown.classList.remove("active");
                }
            }
        });
    }

    // 3. Notification Sidebar
    const notifTrigger = document.getElementById("notifTrigger");
    const notifSidebar = document.getElementById("notifSidebar");
    const notifOverlay = document.getElementById("notifOverlay");
    const closeNotifBtn = document.getElementById("closeNotifBtn");
    const notifBadge = document.getElementById("notifBadge");

    if (notifTrigger && notifSidebar && notifOverlay) {
        notifTrigger.addEventListener("click", (e) => {
            e.stopPropagation();
            notifSidebar.classList.add("active");
            notifOverlay.classList.add("active");
            if (notifBadge) notifBadge.style.display = "none";
        });
    }

    const closeNotificationSidebar = () => {
        if(notifSidebar) notifSidebar.classList.remove("active");
        if(notifOverlay) notifOverlay.classList.remove("active");
    };
    if (closeNotifBtn) closeNotifBtn.addEventListener("click", closeNotificationSidebar);
    if (notifOverlay) notifOverlay.addEventListener("click", closeNotificationSidebar);

    // 4. Avatar Upload Modal
    const changePicBtn = document.getElementById("changePicBtn");
    const avatarUploadModal = document.getElementById("avatarUploadModal");
    const closeAvatarModalBtn = document.getElementById("closeAvatarModalBtn");
    const avatarFileInput = document.getElementById("avatarFileInput");
    const avatarPreview = document.getElementById("avatarPreview");
    const avatarUploadForm = document.getElementById("avatarUploadForm");
    let selectedImageBase64 = null;

    if (changePicBtn && avatarUploadModal) {
        changePicBtn.addEventListener("click", (e) => {
            e.preventDefault();
            if (avatarDropdown) avatarDropdown.classList.remove("active"); 
            avatarUploadModal.classList.add("active"); 
        });
    }

    if (closeAvatarModalBtn) {
        closeAvatarModalBtn.addEventListener("click", () => { avatarUploadModal.classList.remove("active"); });
    }

    if (avatarFileInput && avatarPreview) {
        avatarFileInput.addEventListener("change", (e) => {
            const file = e.target.files[0];
            if (file) {
                if (!file.type.startsWith('image/')) { alert("الرجاء اختيار ملف صورة فقط!"); return; }
                const reader = new FileReader();
                reader.onload = (event) => {
                    avatarPreview.src = event.target.result;
                    selectedImageBase64 = event.target.result; 
                };
                reader.readAsDataURL(file);
            }
        });
    }

    if (avatarUploadForm) {
        avatarUploadForm.addEventListener("submit", (e) => {
            e.preventDefault();
            if (selectedImageBase64) {
                document.querySelectorAll(".user-avatar img, .dropdown-menu img, #mainPageAvatar").forEach(img => { img.src = selectedImageBase64; });
                localStorage.setItem('user_custom_avatar', selectedImageBase64);
                avatarUploadModal.classList.remove("active");
                alert("تم تحديث صورتك الشخصية بنجاح! 👤✨");
            } else {
                alert("الرجاء اختيار صورة أولاً قبل الحفظ.");
            }
        });
    }

    // تطبيق الصورة المحفوظة تلقائياً في كل الصفحات
    const savedAvatar = localStorage.getItem('user_custom_avatar');
    if (savedAvatar) {
        document.querySelectorAll(".user-avatar img, #mainPageAvatar").forEach(img => img.src = savedAvatar);
        if (avatarPreview) avatarPreview.src = savedAvatar;
    }

    // 5. Account Settings Routing & Modal Handler
    const accountSettingsBtn = document.getElementById("accountSettingsBtn");
    if (accountSettingsBtn) {
        accountSettingsBtn.setAttribute("href", "settings.html");
        accountSettingsBtn.addEventListener("click", () => {
            window.location.href = "settings.html";
        });
    }

    const accountSettingsModal = document.getElementById('accountSettingsModal');
    const closeSettingsModalBtn = document.getElementById('closeSettingsModalBtn');
    if (closeSettingsModalBtn) {
        closeSettingsModalBtn.addEventListener('click', () => {
            if(accountSettingsModal) accountSettingsModal.classList.remove('active');
        });
    }

    const pageSettingsForm = document.getElementById("pageSettingsForm");
    if (pageSettingsForm) {
        pageSettingsForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            // هنا يوضع الـ API بتاع تغيير بيانات الحساب لو محتاجه
        });
    }

    // 6. مسح ذاكرة التخزين المؤقت عند تسجيل الخروج (Logout Clearing)
    const logoutElements = document.querySelectorAll('.logout-btn, .logout-link');
    logoutElements.forEach(element => {
        element.addEventListener('click', () => {
            localStorage.removeItem('bookingPrice');
            localStorage.removeItem('bookedVehicle');
            localStorage.removeItem('bookedSlot');
            localStorage.removeItem('selectedGarageName');
        });
    });
});


// 💡 Fetch live slot statuses from DB and update the local layout data dynamically
async function fetchAndRenderLiveSlots(garageId) {
    try {
        const response = await fetch(`/api/get_garage_slots?garage_id=${garageId}`);
        const data = await response.json();

        if (data.status === 'success') {
            const dbSlots = data.slots; // The dictionary coming from Supabase

            // Dynamically update the status in your existing local parkingSlotsData array
            for (const category in parkingSlotsData) {
                parkingSlotsData[category].forEach(slot => {
                    if (dbSlots[slot.id]) {
                        // If DB says 'available', set it to 'available', otherwise mark as 'occupied'
                        slot.status = dbSlots[slot.id] === 'available' ? 'available' : 'occupied';
                    }
                });
            }

            // Render the layout perfectly with the freshly updated live database data
            renderParkingLayout();
        }
    } catch (error) {
        console.error("Error fetching live slot data from server:", error);
    }
}