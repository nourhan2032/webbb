document.addEventListener('DOMContentLoaded', () => {
    // 1. سحب البيانات اللي حفظناها من شاشة الداشبورد في الخطوات اللي فاتت
    const savedGarage = localStorage.getItem('selectedGarageName') || 'Unknown Garage';
    const savedSlot = localStorage.getItem('bookedSlot') || 'N/A';
    const savedVehicle = localStorage.getItem('bookedVehicle') || 'Unknown Plate';
    const savedPrice = localStorage.getItem('bookingPrice') || '0.00';

    // 2. عرض البيانات جوه الـ HTML بتاع التذكرة
    document.getElementById('summary-garage').innerText = savedGarage;
    document.getElementById('summary-slot').innerText = savedSlot;
    document.getElementById('summary-vehicle').innerText = savedVehicle;
    document.getElementById('summary-price').innerText = `${savedPrice} EGP`;

    // 3. برمجة زرار الانتقال لخريطة الملاحة الحية
    const startNavBtn = document.getElementById('startNavigationBtn');
    
    if (startNavBtn) {
        startNavBtn.addEventListener('click', () => {
            // إضافة حركة صغيرة (Loading) في الزرار قبل ما ينقله
            startNavBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Preparing Route...';
            startNavBtn.style.opacity = '0.8';
            startNavBtn.disabled = true;

            // تأخير نص ثانية عشان شكل اللودينج يبان، وبعدين يروح لصفحة الـ Navigation
            setTimeout(() => {
                window.location.href = 'navigation.html'; 
            }, 600);
        });
    }
});