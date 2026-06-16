/* =====================================================
   Theme Toggle Logic (Dark/Light Mode)
===================================================== */
const toggleBtn = document.getElementById("themeToggle");

if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
        // تبديل كلاس الوضع النهاري
        document.body.classList.toggle("light-mode");
        
        // تغيير أيقونة الشمس والقمر
        if (document.body.classList.contains("light-mode")) {
            toggleBtn.innerHTML = '<i class="fa-solid fa-sun"></i>';
        } else {
            toggleBtn.innerHTML = '<i class="fa-solid fa-moon"></i>';
        }
    });
}

/* =====================================================
   Flow State Management
===================================================== */
let chosenAmount = 50; 
let isCustom = false;
let chosenMethod = 'visa';

function showView(viewId) {
    document.querySelectorAll('.flow-view').forEach(el => el.classList.remove('active'));
    document.getElementById(viewId).classList.add('active');
}

/* =====================================================
   Select Amount Logic
===================================================== */
function selectAmount(element, value) {
    const listItems = document.getElementById('view-amount').querySelectorAll('.selection-item');
    listItems.forEach(item => item.classList.remove('selected'));
    element.classList.add('selected');

    const customInputArea = document.getElementById('customInputWrapper');

    if (value === 'custom') {
        isCustom = true;
        customInputArea.style.display = 'block';
        document.getElementById('customInput').focus();
    } else {
        isCustom = false;
        chosenAmount = value;
        customInputArea.style.display = 'none';
    }
}

function confirmAmountAndProceed() {
    if (isCustom) {
        const customVal = document.getElementById('customInput').value;
        if (!customVal || customVal < 10) {
            Swal.fire({
                title: 'Invalid Amount',
                text: 'Please enter a minimum of 10 EGP.',
                icon: 'warning',
                confirmButtonColor: '#00c2b8', // لون البراند
                customClass: { popup: 'rounded-2xl' }
            });
            return;
        }
        chosenAmount = customVal;
    }
    document.getElementById('finalPayBtn').innerText = `Pay ${chosenAmount} EGP`;
    showView('view-method');
}

/* =====================================================
   Payment Processing
===================================================== */
function selectMethod(element, method) {
    const listItems = document.getElementById('view-method').querySelectorAll('.selection-item');
    listItems.forEach(item => item.classList.remove('selected'));
    element.classList.add('selected');
    chosenMethod = method;
}

/* =====================================================
   Payment Processing (Linked to Backend)
===================================================== */
function processFinalPayment() {
    const btn = document.getElementById('finalPayBtn');
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Processing...`;
    btn.style.opacity = '0.8';

    // نبعت الـ Request للـ Backend عشان يزود الفلوس في الداتابيز
    fetch('/api/add_balance', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ amount: parseFloat(chosenAmount) })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            Swal.fire({
                title: 'Success!',
                text: `Successfully added ${chosenAmount} EGP to your wallet.`,
                icon: 'success',
                confirmButtonColor: '#00c2b8',
                customClass: { popup: 'rounded-2xl' }
            }).then(() => {
                
                // تحديث الرصيد ديناميكياً من الداتا اللي راجعة من السيرفر
                let newBalance = parseFloat(data.new_balance);
                let [newInt, newDec] = newBalance.toFixed(2).split('.');
                
                // تحديث الكارت الكبير
                document.getElementById('balance-int').innerText = newInt;
                document.getElementById('balance-dec').innerText = newDec;
                
                // تحديث الرقم اللي فوق في الـ Header لو موجود
                const topBadge = document.getElementById('top-balance-badge');
                if (topBadge) {
                    topBadge.innerText = `${newBalance.toFixed(2)} EGP`;
                }
                
                // إرجاع الزر لشكله الطبيعي
                btn.innerHTML = `Pay ${chosenAmount} EGP`;
                btn.style.opacity = '1';
                showView('view-overview');
            });
        } else {
            // لو حصل خطأ في السيرفر
            Swal.fire('Error!', data.message, 'error');
            btn.innerHTML = `Pay ${chosenAmount} EGP`;
            btn.style.opacity = '1';
        }
    })
    .catch(err => {
        console.error("Error:", err);
        Swal.fire('Error!', 'Something went wrong. Please try again.', 'error');
        btn.innerHTML = `Pay ${chosenAmount} EGP`;
        btn.style.opacity = '1';
    });
}

/* =====================================================
   Save New Card Logic
===================================================== */
function saveNewCard() {
    const btn = document.getElementById('saveCardBtn');
    const newCardInput = document.getElementById('newCardInput').value;
    
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Saving...`;
    btn.style.opacity = '0.8';

    setTimeout(() => {
        if(newCardInput.length >= 4) {
            const last4 = newCardInput.slice(-4);
            document.getElementById('displayCard').innerText = `VisaCard - ${last4}`;
        }
        
        Swal.fire({
            title: 'Card Linked!',
            text: 'Card successfully linked securely.',
            icon: 'success',
            confirmButtonColor: '#00c2b8', // لون البراند
            customClass: { popup: 'rounded-2xl' }
        }).then(() => {
            btn.innerHTML = `Save Payment Method`;
            btn.style.opacity = '1';
            showView('view-overview');
        });
    }, 1500);
}