let map;
let userMarker; 
let currentRoute = null; 
let activeTarget = null; 

let defaultUserIcon;
let navArrowIcon;

// متغير للتحكم في سرعة طلب البيانات من السيرفر عشان ميعملناش Block
let lastEtaUpdate = 0; 

function initNavigationMap() {
    defaultUserIcon = {
        path: google.maps.SymbolPath.CIRCLE,
        fillColor: '#00c2b8',
        fillOpacity: 1,
        strokeColor: 'white',
        strokeWeight: 2,
        scale: 8
    };

    navArrowIcon = {
        path: 'M 0,-12 8,8 0,3 -8,8 z', 
        fillColor: '#FF0000', 
        fillOpacity: 1,
        strokeColor: 'white',
        strokeWeight: 2,
        scale: 2,
        rotation: 0 
    };

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const userLocation = { lat: position.coords.latitude, lng: position.coords.longitude };
                
                map = new google.maps.Map(document.getElementById("map"), {
                    center: userLocation, 
                    zoom: 17, 
                    disableDefaultUI: true
                });

                userMarker = new google.maps.Marker({
                    position: userLocation,
                    map: map,
                    icon: navArrowIcon 
                });

                // 💡 جلب البيانات الديناميكية المحفوظة أثناء عملية الحجز
                const selectedName = localStorage.getItem('navGarageName') || localStorage.getItem('selectedGarageName') || "Downtown Mall";
                const savedLat = parseFloat(localStorage.getItem('navGarageLat'));
                const savedLng = parseFloat(localStorage.getItem('navGarageLng'));

                // قيم افتراضية (Downtown Mall)
                let targetLat = 30.020603909161768;
                let targetLng = 31.416987712121415; 

                // 🎯 لو الإحداثيات الديناميكية موجودة وصحيحة هنستخدمها فوراً
                if (!isNaN(savedLat) && !isNaN(savedLng) && savedLat !== 0 && savedLng !== 0) {
                    targetLat = savedLat;
                    targetLng = savedLng;
                } else {
                    // 💡 نظام احتياطي (Fallback) بناءً على تطابق الأسماء لو المفاتيح الجديدة مفقودة
                    if (selectedName.includes("Festival")) { 
                        targetLat = 30.02902868528596; targetLng = 31.407601026981595; 
                    }
                    else if (selectedName.includes("Citystars")) { 
                        targetLat = 30.073657271502093; targetLng = 31.347216211636002; 
                    }
                    else if (selectedName.includes("Almaza")) { 
                        targetLat = 30.0809616907494; targetLng = 31.364966669278488; 
                    }
                    else if (selectedName.includes("Arabia")) { 
                        targetLat = 30.006855308588154; targetLng = 30.9753847751759; 
                    }
                    else if (selectedName.includes("Egypt")) { 
                        targetLat = 29.973321066050424; targetLng = 31.019307688667926; 
                    }
                    else if (selectedName.includes("Hub")) {
                        targetLat = 30.17856106; targetLng = 31.47277373; 
                    }
                    else if (selectedName.includes("Downtown")) {
                        targetLat = 30.01857747; targetLng = 31.41321381; 
                    }
                }

                const garageLocation = { 
                    lat: targetLat, 
                    lng: targetLng, 
                    name: selectedName 
                };
                
                startLiveRoute(userLocation, garageLocation);
            },
            () => { alert("Please enable location services to use the map successfully."); }
        );
    }
}

// رسم المسار الرئيسي في البداية
function startLiveRoute(startPos, endPos) {
    activeTarget = endPos;
    
    const instructionEl = document.getElementById("nav-instruction");
    if(instructionEl) {
        instructionEl.innerText = `Head towards: ${endPos.name}`;
    }

    const url = `https://router.project-osrm.org/route/v1/driving/${startPos.lng},${startPos.lat};${endPos.lng},${endPos.lat}?geometries=geojson&overview=full`;
    
    fetch(url)
        .then(res => {
            if (!res.ok) throw new Error("Server Error");
            return res.json();
        })
        .then(data => {
            if (data.routes && data.routes.length > 0) {
                const coords = data.routes[0].geometry.coordinates;
                const path = coords.map(c => ({ lat: c[1], lng: c[0] }));
                path.push({lat: endPos.lat, lng: endPos.lng});

                if (currentRoute) currentRoute.setMap(null);

                currentRoute = new google.maps.Polyline({
                    path: path, 
                    geodesic: true, 
                    strokeColor: '#FF0000', 
                    strokeOpacity: 0.8, 
                    strokeWeight: 6, 
                    map: map
                });

                startLiveTracking();
            } else {
                throw new Error("No route found");
            }
        })
        .catch(err => {
            console.warn("Fallback drawing straight line.");
            if (currentRoute) currentRoute.setMap(null);
            currentRoute = new google.maps.Polyline({
                path: [startPos, {lat: endPos.lat, lng: endPos.lng}],
                geodesic: true,
                strokeColor: '#FF0000',
                strokeOpacity: 0.8,
                strokeWeight: 6,
                map: map
            });
            startLiveTracking();
        });
}

// نظام التتبع والوقت الذكي
function startLiveTracking() {
    navigator.geolocation.watchPosition(
        (position) => {
            const currentPos = { lat: position.coords.latitude, lng: position.coords.longitude };
            
            if (userMarker) {
                userMarker.setPosition(currentPos);
                map.setCenter(currentPos); 
                
                if (activeTarget) {
                    // فحص الوصول للجراج بخط مستقيم (لو أقل من 10 متر)
                    const directDistance = calculateDistance(currentPos.lat, currentPos.lng, activeTarget.lat, activeTarget.lng);
                    
                    if (directDistance <= 10) {
                        alert("You have arrived at your destination garage successfully! 🎉");
                        exitNavigation();
                        return; 
                    }

                    // تدوير السهم
                    const targetBearing = calculateBearing(currentPos.lat, currentPos.lng, activeTarget.lat, activeTarget.lng);
                    let currentIcon = userMarker.getIcon();
                    currentIcon.rotation = targetBearing;
                    userMarker.setIcon(currentIcon);

                    // --- الخوارزمية الجديدة لحساب الوقت والزحمة ---
                    const now = Date.now();
                    // نكلم السيرفر كل 10 ثواني بس عشان نجيب المسافة المتبقية الحقيقية من الشوارع
                    if (now - lastEtaUpdate > 10000) {
                        lastEtaUpdate = now;
                        fetchLiveETA(currentPos, activeTarget);
                    }
                }
            }
        },
        (err) => console.error(err),
        { enableHighAccuracy: true, distanceFilter: 1 } // التحديث كل متر حركة
    );
}

// دالة لجلب الوقت الدقيق بناءً على الشوارع المتبقية وتطبيق الزحمة
function fetchLiveETA(startPos, endPos) {
    const url = `https://router.project-osrm.org/route/v1/driving/${startPos.lng},${startPos.lat};${endPos.lng},${endPos.lat}?overview=false`;
    
    fetch(url)
        .then(res => res.json())
        .then(data => {
            if (data.routes && data.routes.length > 0) {
                const routedDistance = data.routes[0].distance; // بالمتر (على الشارع)
                const baseDuration = data.routes[0].duration; // بالثانية (طريق فاضي)

                // محاكاة ذكية للزحمة (Traffic Simulation)
                const currentHour = new Date().getHours();
                let trafficMultiplier = 1.3; // زحمة عادية في مصر

                // لو وقت ذروة (من 8 لـ 10 الصبح) أو (من 2 الظهر لـ 7 بليل)
                if ((currentHour >= 8 && currentHour <= 10) || (currentHour >= 14 && currentHour <= 19)) {
                    trafficMultiplier = 1.8; 
                }

                const realisticSeconds = baseDuration * trafficMultiplier;
                const estimatedMinutes = Math.ceil(realisticSeconds / 60);

                // ==========================================
                // 💡 اللوجيك الجديد: تنسيق الوقت (ساعات ودقائق)
                // ==========================================
                let timeFormatted = "";
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
                // 💡 اللوجيك الجديد: تنسيق المسافة (متر وكيلومتر)
                // ==========================================
                let distanceFormatted = "";
                if (routedDistance < 1000) {
                    distanceFormatted = `(${Math.round(routedDistance)} m)`; // بالمتر لو أقل من 1000
                } else {
                    const km = (routedDistance / 1000).toFixed(1); // بالكيلومتر مع رقم عشري واحد
                    distanceFormatted = `(${km} km)`;
                }

                // تحديث الـ HTML
                const timeEl = document.getElementById("nav-res-time");
                const distEl = document.getElementById("nav-res-dist");
                
                if(timeEl) {
                    timeEl.innerText = timeFormatted;
                    timeEl.style.color = trafficMultiplier > 1.5 ? "#f59e0b" : "#fff"; 
                }
                if(distEl) {
                    distEl.innerText = distanceFormatted;
                }
            }
        })
        .catch(err => console.error("ETA Fetch error:", err));
}

// معادلات رياضية أساسية
function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371000; 
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))); 
}

function calculateBearing(startLat, startLng, endLat, endLng) {
    const lat1 = startLat * Math.PI / 180; 
    const lat2 = endLat * Math.PI / 180;
    const dLng = (endLng - startLng) * Math.PI / 180;
    const y = Math.sin(dLng) * Math.cos(lat2);
    const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
    return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360; 
}

window.exitNavigation = function() {
    window.location.href = 'user-dashboard.html';
};