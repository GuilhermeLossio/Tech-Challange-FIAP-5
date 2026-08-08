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
        button.textContent = button.textContent;
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
})();
