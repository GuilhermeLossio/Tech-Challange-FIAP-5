(function () {
  const CART_STORAGE_KEY = "ecloe_market_cart_v1";
  const LEGACY_MIGRATION_KEY = "ecloe_market_cart_legacy_migrated_v1";
  const CART_VERSION = 1;
  const CART_TTL_MS = 14 * 24 * 60 * 60 * 1000;

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

  function cartIdentity(item) {
    return `${item.product_id}:${item.variant_id || "default"}`;
  }

  function normalizeCartItem(item) {
    if (!item || typeof item !== "object") {
      return null;
    }
    const productId = String(item.product_id || "").trim();
    const variantId = item.variant_id ? String(item.variant_id).trim() : null;
    const quantity = Number(item.quantity);
    const price = Number(item.unit_price_cents);
    if (!productId || !Number.isInteger(quantity) || quantity < 1 || quantity > 9) {
      return null;
    }
    if (!Number.isInteger(price) || price < 0) {
      return null;
    }
    return {
      product_id: productId,
      variant_id: variantId,
      quantity,
      title: String(item.title || productId),
      thumbnail: String(item.thumbnail || "/market/assets/product-placeholder.svg"),
      unit_price_cents: price,
      currency: String(item.currency || "BRL"),
      issues: Array.isArray(item.issues) ? item.issues.map(String) : [],
    };
  }

  function emptyCart() {
    return { version: CART_VERSION, updated_at: Date.now(), expires_at: Date.now() + CART_TTL_MS, items: [] };
  }

  function readLocalCart() {
    try {
      const parsed = JSON.parse(localStorage.getItem(CART_STORAGE_KEY) || "null");
      if (!parsed || parsed.version !== CART_VERSION || Number(parsed.expires_at) <= Date.now()) {
        localStorage.removeItem(CART_STORAGE_KEY);
        return emptyCart();
      }
      const items = Array.isArray(parsed.items)
        ? parsed.items.map(normalizeCartItem).filter(Boolean).slice(0, 50)
        : [];
      return { ...parsed, version: CART_VERSION, items };
    } catch (_error) {
      localStorage.removeItem(CART_STORAGE_KEY);
      return emptyCart();
    }
  }

  function writeLocalCart(items) {
    const now = Date.now();
    const cart = {
      version: CART_VERSION,
      updated_at: now,
      expires_at: now + CART_TTL_MS,
      items: items.map(normalizeCartItem).filter(Boolean).slice(0, 50),
    };
    localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
    renderLocalCart();
    return cart;
  }

  async function migrateLegacyCartOnce() {
    try {
      if (localStorage.getItem(CART_STORAGE_KEY) !== null) return;
      if (localStorage.getItem(LEGACY_MIGRATION_KEY) !== null) return;
      const response = await fetch("/api/market/cart", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Legacy cart could not be loaded.");
      const body = await response.json();
      const legacyItems = Array.isArray(body.cart?.items) ? body.cart.items : [];
      const items = legacyItems.map((item) => ({
        product_id: item.product_id,
        variant_id: item.variant_id || null,
        quantity: Number(item.quantity),
        title: item.title,
        thumbnail: item.thumbnail,
        unit_price_cents: Number(item.unit_price_cents),
        currency: item.currency || "BRL",
        issues: [],
      }));
      localStorage.setItem(LEGACY_MIGRATION_KEY, String(Date.now()));
      writeLocalCart(items);
    } catch (_error) {
      // A failed compatibility read must not prevent the browser-only cart from working.
    }
  }

  async function initializeLocalCart() {
    await migrateLegacyCartOnce();
    renderLocalCart();
  }

  function cartTotals(cart) {
    return {
      total_items: cart.items.reduce((total, item) => total + item.quantity, 0),
      total_cents: cart.items.reduce(
        (total, item) => total + item.quantity * item.unit_price_cents,
        0,
      ),
    };
  }

  function formatMoney(cents, currency = "BRL") {
    return new Intl.NumberFormat(document.documentElement.lang || "en-US", {
      style: "currency",
      currency,
    }).format(cents / 100);
  }

  function updateCartSummary(cart) {
    const totals = cartTotals(cart);
    document.querySelectorAll("[data-cart-count]").forEach((node) => {
      node.textContent = String(totals.total_items);
    });
    document.querySelectorAll("[data-cart-total]").forEach((node) => {
      node.textContent = formatMoney(totals.total_cents);
    });
  }

  function issueMessage(item, root) {
    if (item.issues.includes("quantity_unavailable")) {
      return root?.dataset.stockLabel || "Quantity unavailable; adjust this item.";
    }
    if (item.issues.length) {
      return root?.dataset.cartChangedLabel || "This item requires review.";
    }
    return "";
  }

  function createCartItemNode(item, root) {
    const article = document.createElement("article");
    article.className = "cart-item";
    article.dataset.localCartItem = cartIdentity(item);
    if (item.issues.length) {
      article.classList.add("cart-item-review");
    }

    const image = document.createElement("img");
    image.src = item.thumbnail;
    image.alt = "";
    image.onerror = () => { image.src = "/market/assets/product-placeholder.svg"; };

    const copy = document.createElement("div");
    const title = document.createElement("h2");
    title.textContent = item.title;
    const note = document.createElement("p");
    note.textContent = issueMessage(item, root) || root.dataset.syntheticLabel || "Synthetic item.";
    const unitPrice = document.createElement("strong");
    unitPrice.textContent = formatMoney(item.unit_price_cents, item.currency);
    copy.append(title, note, unitPrice);

    const label = document.createElement("label");
    const labelText = document.createElement("span");
    labelText.textContent = root.dataset.quantityLabel || "Quantity";
    const input = document.createElement("input");
    input.type = "number";
    input.min = "1";
    input.max = "9";
    input.value = String(item.quantity);
    input.dataset.localCartQuantity = cartIdentity(item);
    label.append(labelText, input);

    const subtotal = document.createElement("strong");
    subtotal.textContent = formatMoney(item.quantity * item.unit_price_cents, item.currency);
    const remove = document.createElement("button");
    remove.className = "secondary-link";
    remove.type = "button";
    remove.dataset.localRemoveCartItem = cartIdentity(item);
    remove.textContent = root.dataset.removeLabel || "Remove";
    article.append(image, copy, label, subtotal, remove);
    return article;
  }

  function createCheckoutItemNode(item, root) {
    const article = document.createElement("article");
    article.className = "cart-item checkout-item";
    if (item.issues.length) {
      article.classList.add("cart-item-review");
    }
    const image = document.createElement("img");
    image.src = item.thumbnail;
    image.alt = "";
    image.onerror = () => { image.src = "/market/assets/product-placeholder.svg"; };
    const copy = document.createElement("div");
    copy.className = "checkout-item-copy";
    const title = document.createElement("h2");
    title.textContent = item.title;
    const quantity = document.createElement("p");
    quantity.textContent = `${root.dataset.quantityLabel || "Quantity"}: ${item.quantity}`;
    copy.append(title, quantity);
    const warning = issueMessage(item, root);
    if (warning) {
      const issue = document.createElement("p");
      issue.className = "cart-review-message";
      issue.textContent = warning;
      copy.append(issue);
    }
    const price = document.createElement("strong");
    price.className = "checkout-item-price";
    price.textContent = formatMoney(item.quantity * item.unit_price_cents, item.currency);
    article.append(image, copy, price);
    return article;
  }

  function renderCheckoutItems(items, root) {
    const list = root?.querySelector("[data-local-checkout-items]");
    if (!list) return;
    list.replaceChildren(...items.map((item) => createCheckoutItemNode(item, root)));
  }

  function renderLocalCart() {
    const cart = readLocalCart();
    updateCartSummary(cart);
    const cartRoot = document.querySelector("[data-local-cart-page]");
    if (cartRoot) {
      const list = cartRoot.querySelector("[data-local-cart-items]");
      const empty = cartRoot.querySelector("[data-cart-empty]");
      list.replaceChildren(...cart.items.map((item) => createCartItemNode(item, cartRoot)));
      empty.hidden = cart.items.length > 0;
      list.hidden = cart.items.length === 0;
    }
    const checkoutRoot = document.querySelector("[data-local-checkout-page]");
    if (checkoutRoot) {
      if (!cart.items.length && !checkoutRoot.classList.contains("purchase-complete")) {
        window.location.replace("/market/cart");
        return;
      }
      renderCheckoutItems(cart.items, checkoutRoot);
      const blocksPayment = cart.items.some((item) =>
        item.issues.some((issue) => issue !== "price_changed"),
      );
      const checkoutButton = checkoutRoot.querySelector("[data-start-checkout]");
      if (checkoutButton) {
        checkoutButton.disabled = blocksPayment;
      }
    }
  }

  function addLocalCartItem(button) {
    const cart = readLocalCart();
    const incoming = normalizeCartItem({
      product_id: button.dataset.addProduct,
      variant_id: button.dataset.cartVariant || null,
      quantity: 1,
      title: button.dataset.cartTitle,
      thumbnail: button.dataset.cartThumbnail,
      unit_price_cents: Number(button.dataset.cartPrice),
      currency: button.dataset.cartCurrency || "BRL",
    });
    if (!incoming) {
      throw new Error("Invalid local cart item.");
    }
    const identity = cartIdentity(incoming);
    const existing = cart.items.find((item) => cartIdentity(item) === identity);
    if (existing) {
      existing.quantity = Math.min(existing.quantity + 1, 9);
      existing.title = incoming.title;
      existing.thumbnail = incoming.thumbnail;
      existing.unit_price_cents = incoming.unit_price_cents;
      existing.issues = [];
    } else {
      cart.items.push(incoming);
    }
    writeLocalCart(cart.items);
  }

  function updateLocalQuantity(identity, quantity) {
    const cart = readLocalCart();
    const item = cart.items.find((entry) => cartIdentity(entry) === identity);
    if (!item) {
      return;
    }
    item.quantity = Math.max(1, Math.min(Number(quantity) || 1, 9));
    item.issues = [];
    writeLocalCart(cart.items);
  }

  function removeLocalItem(identity) {
    const cart = readLocalCart();
    writeLocalCart(cart.items.filter((item) => cartIdentity(item) !== identity));
  }

  function showCartToast() {
    const toast = document.querySelector("[data-cart-toast]");
    if (!toast) return;
    toast.hidden = false;
    toast.classList.add("visible");
    window.clearTimeout(showCartToast.timeoutId);
    showCartToast.timeoutId = window.setTimeout(() => {
      toast.classList.remove("visible");
      toast.hidden = true;
    }, 2400);
  }

  function resetAddButton(button) {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.classList.remove("cart-add-pending", "cart-add-success", "cart-add-error");
    button.textContent = button.dataset.addLabel || "Add to cart";
  }

  async function recordRecommendation(button, eventType) {
    if (!button.dataset.recommendationDecision) return;
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
      // Local cart remains usable when optional recommendation telemetry is unavailable.
    }
  }

  document.querySelectorAll("[data-add-product]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.classList.add("cart-add-pending");
      button.textContent = button.dataset.addingLabel || "Adding...";
      try {
        addLocalCartItem(button);
        void recordRecommendation(button, "add_to_cart");
        button.classList.remove("cart-add-pending");
        button.classList.add("cart-add-success");
        button.removeAttribute("aria-busy");
        button.textContent = button.dataset.addedLabel || "Added";
        showCartToast();
      } catch (_error) {
        button.classList.remove("cart-add-pending");
        button.classList.add("cart-add-error");
        button.textContent = button.dataset.failedLabel || "Try again";
      }
      window.setTimeout(() => resetAddButton(button), 1400);
    });
  });

  document.addEventListener("change", (event) => {
    const input = event.target.closest?.("[data-local-cart-quantity]");
    if (input) updateLocalQuantity(input.dataset.localCartQuantity, input.value);
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-local-remove-cart-item]");
    if (button) removeLocalItem(button.dataset.localRemoveCartItem);
  });

  function checkoutPayload(items) {
    return items.map((item) => ({
      product_id: item.product_id,
      variant_id: item.variant_id,
      quantity: item.quantity,
      expected_unit_price_cents: item.unit_price_cents,
    }));
  }

  function applyReviewedItems(reviewedItems) {
    const cart = readLocalCart();
    reviewedItems.forEach((reviewed) => {
      const existing = cart.items.find((item) =>
        item.product_id === reviewed.product_id
        && (!item.variant_id || !reviewed.variant_id || item.variant_id === reviewed.variant_id),
      );
      if (!existing) return;
      existing.variant_id = reviewed.variant_id || existing.variant_id;
      existing.title = reviewed.title || existing.title;
      existing.thumbnail = reviewed.thumbnail || existing.thumbnail;
      if (Number.isInteger(reviewed.current_unit_price_cents)) {
        existing.unit_price_cents = reviewed.current_unit_price_cents;
      }
      existing.currency = reviewed.currency || existing.currency;
      existing.issues = Array.isArray(reviewed.issues) ? reviewed.issues : [];
    });
    return writeLocalCart(cart.items);
  }

  function subtractPurchasedItems(purchased) {
    const cart = readLocalCart();
    purchased.forEach((bought) => {
      const item = cart.items.find((entry) =>
        entry.product_id === bought.product_id
        && (!entry.variant_id || !bought.variant_id || entry.variant_id === bought.variant_id),
      );
      if (!item) return;
      item.quantity -= Number(bought.quantity) || 0;
    });
    writeLocalCart(cart.items.filter((item) => item.quantity > 0));
  }

  const checkoutButton = document.querySelector("[data-start-checkout]");
  const checkoutStatus = document.querySelector("[data-checkout-status]");
  const purchaseConfirmation = document.querySelector("[data-purchase-confirmation]");
  if (checkoutButton && checkoutStatus) {
    checkoutButton.addEventListener("click", async () => {
      const initialCart = readLocalCart();
      if (!initialCart.items.length) {
        window.location.assign("/market/cart");
        return;
      }
      checkoutButton.disabled = true;
      checkoutStatus.textContent = "";
      try {
        const checkoutResponse = await fetch("/api/market/checkouts", {
          method: "POST",
          headers: { ...csrfHeaders(), "Idempotency-Key": `checkout-${crypto.randomUUID()}` },
          body: JSON.stringify({ items: checkoutPayload(initialCart.items) }),
        });
        const checkoutBody = await checkoutResponse.json();
        if (checkoutResponse.status === 409 && checkoutBody.code === "cart_changed") {
          if (Array.isArray(checkoutBody.items)) applyReviewedItems(checkoutBody.items);
          throw new Error(
            document.querySelector("[data-local-checkout-page]")?.dataset.cartChangedLabel
            || checkoutBody.error,
          );
        }
        if (!checkoutResponse.ok) throw new Error(checkoutBody.error || "Checkout could not be started.");
        const reviewedCart = Array.isArray(checkoutBody.items)
          ? applyReviewedItems(checkoutBody.items)
          : initialCart;
        // Keep the reviewed cart snapshot so the confirmation screen can show
        // what was actually paid after those items leave localStorage.
        const purchasedItems = reviewedCart.items.map((item) => ({ ...item, issues: [] }));
        const orderResponse = await fetch("/api/market/orders", {
          method: "POST",
          headers: csrfHeaders(),
          body: JSON.stringify({ checkout_id: checkoutBody.checkout.checkout_id }),
        });
        const orderBody = await orderResponse.json();
        if (!orderResponse.ok) throw new Error(orderBody.error || "Order could not be created.");
        const paymentResponse = await fetch(`/api/market/orders/${orderBody.order.order_id}/pay`, {
          method: "POST",
          headers: { ...csrfHeaders(), "Idempotency-Key": `wallet-${orderBody.order.order_id}` },
        });
        const paymentBody = await paymentResponse.json();
        if (!paymentResponse.ok) throw new Error(paymentBody.error || "Wallet payment could not be completed.");
        document.querySelector(".checkout-page").classList.add("purchase-complete");
        subtractPurchasedItems(purchasedItems);
        renderCheckoutItems(purchasedItems, document.querySelector("[data-local-checkout-page]"));
        checkoutStatus.textContent = `${paymentBody.order.order_id} - ${paymentBody.order.status}`;
        checkoutButton.hidden = true;
        if (purchaseConfirmation) {
          const locale = document.documentElement.lang || "en-US";
          purchaseConfirmation.querySelector("[data-confirmation-order]").textContent = paymentBody.order.order_id;
          purchaseConfirmation.querySelector("[data-confirmation-total]").textContent = new Intl.NumberFormat(
            locale, { style: "currency", currency: "BRL" },
          ).format(paymentBody.order.total_cents / 100);
          purchaseConfirmation.querySelector("[data-confirmation-date]").textContent = new Intl.DateTimeFormat(
            locale, { dateStyle: "medium", timeStyle: "short" },
          ).format(new Date());
          purchaseConfirmation.hidden = false;
          purchaseConfirmation.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      } catch (error) {
        checkoutStatus.textContent = error.message;
        checkoutButton.disabled = readLocalCart().items.some((item) =>
          item.issues.some((issue) => issue !== "price_changed"),
        );
      }
    });
  }

  const galleryMain = document.querySelector("[data-product-gallery-main]");
  document.querySelectorAll("[data-gallery-image]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!galleryMain) return;
      galleryMain.src = button.dataset.galleryImage;
      document.querySelectorAll("[data-gallery-image]").forEach((thumb) => {
        thumb.classList.toggle("active", thumb === button);
      });
    });
  });

  window.addEventListener("storage", (event) => {
    if (event.key === CART_STORAGE_KEY) renderLocalCart();
  });
  void initializeLocalCart();
})();
