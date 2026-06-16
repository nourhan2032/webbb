// متغيرات عشان نحفظ الـ IDs بتاعت الحجز اللي اليوزر اختاره
let currentCancelId = null;
let currentCheckoutId = null;

// ==========================================
// 1. دوال فتح وقفل المودالز (Popups)
// ==========================================

function openCancelModal(reservId, plateNo) {
    currentCancelId = reservId;
    const modal = document.getElementById('cancel-modal');
    if (modal) {
        modal.classList.add('show');
        modal.style.display = 'flex'; 
        modal.style.visibility = 'visible';
        modal.style.opacity = '1';
        modal.style.zIndex = '999999'; 
        
        const plateElement = document.getElementById('cancel-plate');
        if(plateElement) {
            plateElement.innerText = plateNo;
        }
    }
}

// تعديل: المودال بقى يقرأ السعر والوقت اللحظي من الشاشة وقت ما تدوسي عليه
function openCheckoutModal(reservId) {
    currentCheckoutId = reservId;
    const modal = document.getElementById('checkout-modal');
    
    if (modal) {
        const livePriceElem = document.getElementById(`live-price-${reservId}`);
        const liveTimeElem = document.getElementById(`live-time-${reservId}`);
        
        const priceElement = document.getElementById('checkout-price');
        if (priceElement && livePriceElem) {
            priceElement.innerText = parseFloat(livePriceElem.innerText).toFixed(2);
        }
        
        const durationElement = document.getElementById('checkout-duration');
        if (durationElement && liveTimeElem) {
            durationElement.innerText = liveTimeElem.innerText;
        }

        modal.classList.add('show');
        modal.style.display = 'flex'; 
        modal.style.visibility = 'visible';
        modal.style.opacity = '1';
        modal.style.zIndex = '999999'; 
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('show');
        modal.style.opacity = '0';
        setTimeout(() => { 
            modal.style.display = 'none'; 
            modal.style.visibility = 'hidden';
        }, 300); 
    }
}

// ==========================================
// 2. ربط زراير التأكيد والعداد اللايف
// ==========================================

document.addEventListener('DOMContentLoaded', () => {

    // 🕒 الموتور: بيشتغل كل 60 ثانية (دقيقة) ويحدث العداد والسعر
    setInterval(() => {
        const timers = document.querySelectorAll('.live-timer');
        timers.forEach(timer => {
            const timeText = timer.innerText;
            // بيستخرج الساعات والدقايق (مثال بيقرأ 1h 35m)
            const match = timeText.match(/(\d+)h\s*(\d+)m/);
            
            if (match) {
                let hours = parseInt(match[1]);
                let mins = parseInt(match[2]);
                
                // نزود دقيقة
                let totalMins = (hours * 60) + mins + 1; 
                let newHours = Math.floor(totalMins / 60);
                let newMins = totalMins % 60;
                
                // نحدث العداد في الشاشة
                timer.innerText = `${newHours}h ${newMins}m`;
                
                // نحسب السعر الجديد (لو عدى 30 دقيقة بيتحسب ساعة كاملة)
                let billedHours = newHours;
                if (newMins >= 30) {
                    billedHours += 1;
                }
                billedHours = Math.max(1, billedHours);
                
                let hourlyPrice = parseFloat(timer.getAttribute('data-price'));
                let newPrice = billedHours * hourlyPrice;
                
                // نحدث السعر في الشاشة
                const priceId = timer.getAttribute('data-id');
                const priceElem = document.getElementById(`live-price-${priceId}`);
                if (priceElem) {
                    priceElem.innerText = newPrice.toFixed(2) + " EGP";
                }
            }
        });
    }, 60000); // 60000 ms = 1 minute

    // -----------------------------------------------------
    // تأكيد الإلغاء
    // -----------------------------------------------------
    const confirmCancelBtn = document.getElementById('confirm-cancel-btn');
    if (confirmCancelBtn) {
        confirmCancelBtn.addEventListener('click', function() {
            if (!currentCancelId) return;
            
            const btn = this;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Cancelling...';
            btn.style.opacity = '0.8';

            fetch('/api/cancel_reservation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reserv_id: currentCancelId })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    closeModal('cancel-modal');
                    Swal.fire({
                        title: 'Cancelled!',
                        text: data.message,
                        icon: 'success',
                        confirmButtonColor: '#ef4444', 
                        customClass: { popup: 'rounded-2xl' }
                    }).then(() => {
                        location.reload(); 
                    });
                } else {
                    Swal.fire('Error', data.message, 'error');
                    btn.innerHTML = 'Confirm Cancel';
                    btn.style.opacity = '1';
                }
            })
            .catch(error => {
                console.error("Error:", error);
                Swal.fire('Error', 'Something went wrong while cancelling.', 'error');
                btn.innerHTML = 'Confirm Cancel';
                btn.style.opacity = '1';
            });
        });
    }

    // -----------------------------------------------------
    // تأكيد الدفع (Check Out)
    // -----------------------------------------------------
    const confirmCheckoutBtn = document.getElementById('confirm-checkout-btn');
    if (confirmCheckoutBtn) {
        confirmCheckoutBtn.addEventListener('click', function() {
            
            let priceElement = document.getElementById('checkout-price');
            let amountToPay = priceElement ? parseFloat(priceElement.innerText) : 0.0;

            const btn = this;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
            btn.style.opacity = '0.8';

            fetch('/api/process_payment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: amountToPay })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    
                    const topBadge = document.getElementById('top-balance-badge');
                    if (topBadge && data.new_balance !== undefined) {
                        topBadge.innerHTML = `${data.new_balance.toFixed(2)} EGP`;
                    }

                    closeModal('checkout-modal'); 

                    Swal.fire({
                        title: 'Success!',
                        text: 'Checkout completed & payment deducted successfully!',
                        icon: 'success',
                        confirmButtonColor: '#00c2b8',
                        customClass: { popup: 'rounded-2xl' }
                    }).then(() => {
                        location.reload(); 
                    });

                } else {
                    Swal.fire('Error!', data.message, 'error');
                    btn.innerHTML = 'Confirm Check Out';
                    btn.style.opacity = '1';
                }
            })
            .catch(error => {
                console.error("Error:", error);
                Swal.fire('Error', 'Something went wrong during checkout.', 'error');
                btn.innerHTML = 'Confirm Check Out';
                btn.style.opacity = '1';
            });
        });
    }
});