(function () {
  function cookieValue(name) {
    return document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(`${name}=`))
      ?.split("=")
      .slice(1)
      .join("=") || "";
  }

  function csrfHeaders() {
    return {
      "Content-Type": "application/json",
      "X-CSRF-Token": decodeURIComponent(cookieValue("ecloe_pay_csrf")),
    };
  }

  function updateCartCount(cart) {
    document.querySelectorAll("[data-cart-count]").forEach((node) => {
      node.textContent = String(cart.total_items || 0);
    });
  }

  function showCartToast() {
    const toast = document.querySelector("[data-cart-toast]");
    if (!toast) {
      return;
    }
    toast.hidden = false;
    toast.classList.add("visible");
    window.clearTimeout(showCartToast.timeoutId);
    showCartToast.timeoutId = window.setTimeout(() => {
      toast.classList.remove("visible");
      toast.hidden = true;
    }, 2400);
  }

  async function mutateCart(url, options) {
    const response = await fetch(url, {
      ...options,
      headers: csrfHeaders(),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || "Cart update failed.");
    }
    updateCartCount(body.cart);
    return body.cart;
  }

  async function recordRecommendation(button, eventType) {
    if (!button.dataset.recommendationDecision) {
      return;
    }
    try {
      await fetch("/api/market/recommendations/feedback", {
        method: "POST",
        headers: csrfHeaders(),
        body: JSON.stringify({
          decision_id: button.dataset.recommendationDecision,
          product_id: button.dataset.addProduct,
          position: Number(button.dataset.recommendationPosition || 0),
          event_type: eventType,
        }),
      });
    } catch (_error) {
      // Cart updates remain usable when optional recommendation telemetry is unavailable.
    }
  }

  document.querySelectorAll("[data-add-product]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await mutateCart("/api/market/cart/items", {
          method: "POST",
          body: JSON.stringify({
            product_id: button.dataset.addProduct,
            quantity: 1,
          }),
        });
        await recordRecommendation(button, "add_to_cart");
        showCartToast();
      } finally {
        button.disabled = false;
      }
    });
  });

  document.querySelectorAll("[data-cart-quantity]").forEach((input) => {
    input.addEventListener("change", async () => {
      await mutateCart(`/api/market/cart/items/${input.dataset.cartQuantity}`, {
        method: "PATCH",
        body: JSON.stringify({ quantity: Number(input.value || 1) }),
      });
      window.location.reload();
    });
  });

  document.querySelectorAll("[data-remove-cart-item]").forEach((button) => {
    button.addEventListener("click", async () => {
      await mutateCart(`/api/market/cart/items/${button.dataset.removeCartItem}`, {
        method: "DELETE",
      });
      window.location.reload();
    });
  });

  const checkoutButton = document.querySelector("[data-start-checkout]");
  const checkoutStatus = document.querySelector("[data-checkout-status]");
  if (checkoutButton && checkoutStatus) {
    checkoutButton.addEventListener("click", async () => {
      checkoutButton.disabled = true;
      checkoutStatus.textContent = "";
      try {
        const checkoutResponse = await fetch("/api/market/checkouts", {
          method: "POST",
          headers: {
            ...csrfHeaders(),
            "Idempotency-Key": `checkout-${crypto.randomUUID()}`,
          },
        });
        const checkoutBody = await checkoutResponse.json();
        if (!checkoutResponse.ok) {
          throw new Error(checkoutBody.error || "Checkout could not be started.");
        }
        const orderResponse = await fetch("/api/market/orders", {
          method: "POST",
          headers: csrfHeaders(),
          body: JSON.stringify({ checkout_id: checkoutBody.checkout.checkout_id }),
        });
        const orderBody = await orderResponse.json();
        if (!orderResponse.ok) {
          throw new Error(orderBody.error || "Order could not be created.");
        }
        const paymentResponse = await fetch(`/api/market/orders/${orderBody.order.order_id}/pay`, {
          method: "POST",
          headers: {
            ...csrfHeaders(),
            "Idempotency-Key": `wallet-${orderBody.order.order_id}`,
          },
        });
        const paymentBody = await paymentResponse.json();
        if (!paymentResponse.ok) {
          throw new Error(paymentBody.error || "Wallet payment could not be completed.");
        }
        checkoutStatus.textContent = `${paymentBody.order.order_id} - ${paymentBody.order.status}`;
        checkoutButton.hidden = true;
      } catch (error) {
        checkoutStatus.textContent = error.message;
        checkoutButton.disabled = false;
      }
    });
  }

  const galleryMain = document.querySelector("[data-product-gallery-main]");
  document.querySelectorAll("[data-gallery-image]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!galleryMain) {
        return;
      }
      galleryMain.src = button.dataset.galleryImage;
      document.querySelectorAll("[data-gallery-image]").forEach((thumb) => {
        thumb.classList.toggle("active", thumb === button);
      });
    });
  });
})();
