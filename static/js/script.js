/**
 * script.js - Client-Side Interactivity for E-Commerce Recommendation Engine
 * =========================================================================
 * Beginner-friendly JavaScript handling:
 * 1. Password show/hide toggle on login/register forms
 * 2. Quantity selector (+ / -) with stock limitation checks
 * 3. Alert dismissal
 */

document.addEventListener("DOMContentLoaded", function () {
    // -------------------------------------------------------------
    // 1. Password Visibility Toggle
    // -------------------------------------------------------------
    const toggleButtons = document.querySelectorAll(".password-toggle-btn");
    toggleButtons.forEach(button => {
        button.addEventListener("click", function () {
            const targetId = this.getAttribute("data-target");
            const input = document.getElementById(targetId);
            if (input) {
                if (input.type === "password") {
                    input.type = "text";
                    this.textContent = "🙈"; // Hide icon
                    this.setAttribute("aria-label", "Hide password");
                } else {
                    input.type = "password";
                    this.textContent = "👁️"; // Show icon
                    this.setAttribute("aria-label", "Show password");
                }
            }
        });
    });

    // -------------------------------------------------------------
    // 2. Quantity Counter Controls (Product Details Page)
    // -------------------------------------------------------------
    const qtyInput = document.getElementById("product-quantity-input");
    const qtyBtnPlus = document.getElementById("qty-btn-plus");
    const qtyBtnMinus = document.getElementById("qty-btn-minus");

    if (qtyInput && qtyBtnPlus && qtyBtnMinus) {
        const maxStock = parseInt(qtyInput.getAttribute("max") || "999", 10);
        const minQty = parseInt(qtyInput.getAttribute("min") || "1", 10);

        qtyBtnPlus.addEventListener("click", function () {
            let current = parseInt(qtyInput.value, 10) || 1;
            if (current < maxStock) {
                qtyInput.value = current + 1;
            } else {
                alert("Cannot exceed available stock of " + maxStock + " units.");
            }
        });

        qtyBtnMinus.addEventListener("click", function () {
            let current = parseInt(qtyInput.value, 10) || 1;
            if (current > minQty) {
                qtyInput.value = current - 1;
            }
        });

        qtyInput.addEventListener("change", function () {
            let current = parseInt(qtyInput.value, 10);
            if (isNaN(current) || current < minQty) {
                qtyInput.value = minQty;
            } else if (current > maxStock) {
                qtyInput.value = maxStock;
                alert("Maximum available stock is " + maxStock + " units.");
            }
        });
    }

    // -------------------------------------------------------------
    // 3. Alert auto-dismissal
    // -------------------------------------------------------------
    const alertCloseButtons = document.querySelectorAll(".alert-close");
    alertCloseButtons.forEach(btn => {
        btn.addEventListener("click", function () {
            const alertBox = this.closest(".alert");
            if (alertBox) {
                alertBox.style.opacity = "0";
                setTimeout(() => alertBox.remove(), 250);
            }
        });
    });

    // Auto-dismiss alerts after 5 seconds
    setTimeout(function () {
        const alerts = document.querySelectorAll(".alert");
        alerts.forEach(alert => {
            alert.style.transition = "opacity 0.5s ease";
            alert.style.opacity = "0";
            setTimeout(() => alert.remove(), 500);
        });
    }, 6000);
});
