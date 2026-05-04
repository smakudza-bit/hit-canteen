const products = [
  {
    id: 1,
    name: "Makita 18V Cordless Drill Kit",
    category: "Power Tools",
    description: "Brushless drill with 2 batteries, charger, and contractor carry case.",
    priceUsd: 189,
    priceZig: 5103,
    rating: 4.8,
    stock: "In Stock",
    delivery: "Harare same day",
    visual: "DRILL",
  },
  {
    id: 2,
    name: "RapidSet Portland Cement 50kg",
    category: "Building Materials",
    description: "Reliable all-purpose cement for slabs, walls, and structural work.",
    priceUsd: 14,
    priceZig: 378,
    rating: 4.6,
    stock: "Bulk Ready",
    delivery: "Nationwide delivery",
    visual: "CEMENT",
  },
  {
    id: 3,
    name: "PEX Plumbing Starter Bundle",
    category: "Plumbing Supplies",
    description: "Pipes, fittings, tape, and pressure connectors for fast installation.",
    priceUsd: 74,
    priceZig: 1998,
    rating: 4.5,
    stock: "In Stock",
    delivery: "Harare next day",
    visual: "PIPES",
  },
  {
    id: 4,
    name: "Industrial Extension Reel 30m",
    category: "Electrical Equipment",
    description: "Heavy-duty outdoor cable reel built for jobsite power distribution.",
    priceUsd: 59,
    priceZig: 1593,
    rating: 4.7,
    stock: "Low Stock",
    delivery: "Bulawayo 2 days",
    visual: "REEL",
  },
  {
    id: 5,
    name: "WeatherShield Roof Sheet Pack",
    category: "Roofing Materials",
    description: "Color-coated roofing sheets with fasteners and ridge cap options.",
    priceUsd: 248,
    priceZig: 6696,
    rating: 4.9,
    stock: "In Stock",
    delivery: "Project delivery",
    visual: "ROOF",
  },
  {
    id: 6,
    name: "ProGuard Safety PPE Set",
    category: "Safety Equipment",
    description: "Helmet, gloves, goggles, dust masks, and reflective vest in one kit.",
    priceUsd: 36,
    priceZig: 972,
    rating: 4.4,
    stock: "In Stock",
    delivery: "Ready for pickup",
    visual: "PPE",
  },
  {
    id: 7,
    name: "Titan Adjustable Spanner Set",
    category: "Hand Tools",
    description: "Chrome-finished adjustable spanners sized for workshop and site use.",
    priceUsd: 28,
    priceZig: 756,
    rating: 4.3,
    stock: "In Stock",
    delivery: "Mutare 2 days",
    visual: "TOOLS",
  },
  {
    id: 8,
    name: "UltraCover Exterior Paint 20L",
    category: "Paint and Accessories",
    description: "UV-resistant exterior paint for homes, shops, and perimeter walls.",
    priceUsd: 92,
    priceZig: 2484,
    rating: 4.7,
    stock: "Low Stock",
    delivery: "Harare same day",
    visual: "PAINT",
  },
  {
    id: 9,
    name: "AgriFlow Hose and Nozzle Kit",
    category: "Gardening Tools",
    description: "Flexible garden hose bundle with spray nozzles and connectors.",
    priceUsd: 42,
    priceZig: 1134,
    rating: 4.2,
    stock: "In Stock",
    delivery: "Nationwide delivery",
    visual: "HOSE",
  },
  {
    id: 10,
    name: "SiteMaster Concrete Mixer 140L",
    category: "Construction Equipment",
    description: "Portable concrete mixer suited for housing projects and small crews.",
    priceUsd: 540,
    priceZig: 14580,
    rating: 4.8,
    stock: "Pre-order",
    delivery: "Project delivery",
    visual: "MIXER",
  },
  {
    id: 11,
    name: "CircuitSafe Consumer Unit Board",
    category: "Electrical Equipment",
    description: "Compact board with breakers for home and office electrical setups.",
    priceUsd: 118,
    priceZig: 3186,
    rating: 4.6,
    stock: "In Stock",
    delivery: "Harare next day",
    visual: "BOARD",
  },
  {
    id: 12,
    name: "Bricklayer Precision Starter Pack",
    category: "Building Materials",
    description: "Trowel, float, line pins, spirit level, and masonry accessories.",
    priceUsd: 64,
    priceZig: 1728,
    rating: 4.5,
    stock: "In Stock",
    delivery: "Ready for pickup",
    visual: "BRICK",
  },
];

const state = {
  category: "All",
  price: "All",
  sort: "featured",
  query: "",
  cart: [],
  wishlist: [],
  wishlistOnly: false,
};

const productGrid = document.getElementById("product-grid");
const productTemplate = document.getElementById("product-card-template");
const categoryStrip = document.getElementById("category-strip");
const categoryFilter = document.getElementById("category-filter");
const priceFilter = document.getElementById("price-filter");
const sortFilter = document.getElementById("sort-filter");
const resultsSummary = document.getElementById("results-summary");
const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const cartItems = document.getElementById("cart-items");
const cartSubtotal = document.getElementById("cart-subtotal");
const cartTotal = document.getElementById("cart-total");
const cartCount = document.getElementById("cart-count");
const wishlistCount = document.getElementById("wishlist-count");
const wishlistTrigger = document.getElementById("wishlist-trigger");
const cartDrawer = document.getElementById("cart-drawer");
const cartTrigger = document.getElementById("cart-trigger");
const drawerClose = document.getElementById("drawer-close");
const drawerOverlay = document.getElementById("drawer-overlay");

const categories = ["All", ...new Set(products.map((product) => product.category))];

function formatUsd(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
}

function formatZig(value) {
  return `ZiG ${value.toLocaleString("en-US")}`;
}

function createCategoryControls() {
  categories.forEach((category) => {
    const chip = document.createElement("button");
    chip.className = `category-chip${category === "All" ? " is-active" : ""}`;
    chip.textContent = category;
    chip.type = "button";
    chip.addEventListener("click", () => {
      state.category = category;
      categoryFilter.value = category;
      updateCategoryHighlight();
      renderProducts();
    });
    categoryStrip.appendChild(chip);

    if (category !== "All") {
      const option = document.createElement("option");
      option.value = category;
      option.textContent = category;
      categoryFilter.appendChild(option);
    }
  });
}

function updateCategoryHighlight() {
  [...categoryStrip.children].forEach((chip) => {
    chip.classList.toggle("is-active", chip.textContent === state.category);
  });
}

function filterProducts() {
  let filtered = [...products];

  if (state.category !== "All") {
    filtered = filtered.filter((product) => product.category === state.category);
  }

  if (state.price !== "All") {
    filtered = filtered.filter((product) => {
      if (state.price === "0-50") return product.priceUsd < 50;
      if (state.price === "50-200") return product.priceUsd >= 50 && product.priceUsd <= 200;
      if (state.price === "200-500") return product.priceUsd > 200 && product.priceUsd <= 500;
      if (state.price === "500+") return product.priceUsd > 500;
      return true;
    });
  }

  if (state.query.trim()) {
    const query = state.query.trim().toLowerCase();
    filtered = filtered.filter((product) =>
      [product.name, product.category, product.description, product.visual]
        .join(" ")
        .toLowerCase()
        .includes(query)
    );
  }

  if (state.wishlistOnly) {
    filtered = filtered.filter((product) => state.wishlist.includes(product.id));
  }

  if (state.sort === "price-asc") {
    filtered.sort((a, b) => a.priceUsd - b.priceUsd);
  } else if (state.sort === "price-desc") {
    filtered.sort((a, b) => b.priceUsd - a.priceUsd);
  } else if (state.sort === "rating") {
    filtered.sort((a, b) => b.rating - a.rating);
  }

  return filtered;
}

function renderProducts() {
  const filtered = filterProducts();
  productGrid.innerHTML = "";

  if (!filtered.length) {
    productGrid.innerHTML = `
      <div class="empty-state">
        <h3>No products matched your search.</h3>
        <p>Try another category, a wider price range, or a simpler search term.</p>
      </div>
    `;
    resultsSummary.textContent = "0 products";
    return;
  }

  filtered.forEach((product) => {
    const node = productTemplate.content.firstElementChild.cloneNode(true);
    const media = node.querySelector(".product-media");
    const category = node.querySelector(".product-category");
    const name = node.querySelector(".product-name");
    const description = node.querySelector(".product-description");
    const usdPrice = node.querySelector(".usd-price");
    const zigPrice = node.querySelector(".zig-price");
    const rating = node.querySelector(".rating");
    const stock = node.querySelector(".stock-chip");
    const delivery = node.querySelector(".delivery-badge");
    const wishlistToggle = node.querySelector(".wishlist-toggle");
    const quickView = node.querySelector(".quick-view");
    const addToCart = node.querySelector(".add-to-cart");

    const visual = document.createElement("div");
    visual.className = "product-visual";
    visual.textContent = product.visual;
    media.appendChild(visual);

    category.textContent = product.category;
    name.textContent = product.name;
    description.textContent = product.description;
    usdPrice.textContent = formatUsd(product.priceUsd);
    zigPrice.textContent = formatZig(product.priceZig);
    rating.textContent = `${product.rating} / 5 rating`;
    stock.textContent = product.stock;
    delivery.textContent = product.delivery;
    wishlistToggle.classList.toggle("is-active", state.wishlist.includes(product.id));
    wishlistToggle.textContent = state.wishlist.includes(product.id) ? "x" : "+";

    wishlistToggle.addEventListener("click", () => toggleWishlist(product.id));
    quickView.addEventListener("click", () => {
      searchInput.value = product.name;
      state.query = product.name;
      renderProducts();
    });
    addToCart.addEventListener("click", () => addToCartItem(product.id));

    productGrid.appendChild(node);
  });

  resultsSummary.textContent = `${filtered.length} products`;
}

function toggleWishlist(productId) {
  if (state.wishlist.includes(productId)) {
    state.wishlist = state.wishlist.filter((id) => id !== productId);
  } else {
    state.wishlist = [...state.wishlist, productId];
  }
  wishlistCount.textContent = state.wishlist.length;
  if (state.wishlistOnly && !state.wishlist.length) {
    state.wishlistOnly = false;
  }
  wishlistTrigger.classList.toggle("is-active", state.wishlistOnly);
  renderProducts();
}

function addToCartItem(productId) {
  const existing = state.cart.find((item) => item.productId === productId);
  if (existing) {
    existing.quantity += 1;
  } else {
    state.cart.push({ productId, quantity: 1 });
  }
  renderCart();
  openCart();
}

function updateQuantity(productId, delta) {
  const item = state.cart.find((entry) => entry.productId === productId);
  if (!item) return;

  item.quantity += delta;
  if (item.quantity <= 0) {
    state.cart = state.cart.filter((entry) => entry.productId !== productId);
  }
  renderCart();
}

function renderCart() {
  cartItems.innerHTML = "";
  cartCount.textContent = state.cart.reduce((sum, item) => sum + item.quantity, 0);

  if (!state.cart.length) {
    cartItems.innerHTML = `
      <div class="empty-state">
        <h3>Your cart is empty.</h3>
        <p>Add products to start checkout with EcoCash, OneMoney, or delivery on site.</p>
      </div>
    `;
    cartSubtotal.textContent = formatUsd(0);
    cartTotal.textContent = formatUsd(8);
    return;
  }

  const subtotal = state.cart.reduce((sum, item) => {
    const product = products.find((entry) => entry.id === item.productId);
    return sum + product.priceUsd * item.quantity;
  }, 0);

  state.cart.forEach((item) => {
    const product = products.find((entry) => entry.id === item.productId);
    const element = document.createElement("article");
    element.className = "cart-item";
    element.innerHTML = `
      <h4>${product.name}</h4>
      <div class="cart-line">
        <span>${formatUsd(product.priceUsd)} each</span>
        <strong>${formatUsd(product.priceUsd * item.quantity)}</strong>
      </div>
      <div class="cart-line">
        <small>${product.delivery}</small>
        <div class="qty-actions">
          <button type="button" data-delta="-1">-</button>
          <span>${item.quantity}</span>
          <button type="button" data-delta="1">+</button>
        </div>
      </div>
    `;

    element.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () =>
        updateQuantity(product.id, Number(button.dataset.delta))
      );
    });

    cartItems.appendChild(element);
  });

  cartSubtotal.textContent = formatUsd(subtotal);
  cartTotal.textContent = formatUsd(subtotal + 8);
}

function openCart() {
  cartDrawer.classList.add("is-open");
  cartDrawer.setAttribute("aria-hidden", "false");
  drawerOverlay.hidden = false;
}

function closeCart() {
  cartDrawer.classList.remove("is-open");
  cartDrawer.setAttribute("aria-hidden", "true");
  drawerOverlay.hidden = true;
}

categoryFilter.addEventListener("change", (event) => {
  state.category = event.target.value;
  updateCategoryHighlight();
  renderProducts();
});

priceFilter.addEventListener("change", (event) => {
  state.price = event.target.value;
  renderProducts();
});

sortFilter.addEventListener("change", (event) => {
  state.sort = event.target.value;
  renderProducts();
});

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.query = searchInput.value;
  renderProducts();
});

wishlistTrigger.addEventListener("click", () => {
  state.wishlistOnly = !state.wishlistOnly;
  wishlistTrigger.classList.toggle("is-active", state.wishlistOnly);
  renderProducts();
});

cartTrigger.addEventListener("click", openCart);
drawerClose.addEventListener("click", closeCart);
drawerOverlay.addEventListener("click", closeCart);

createCategoryControls();
renderProducts();
renderCart();
