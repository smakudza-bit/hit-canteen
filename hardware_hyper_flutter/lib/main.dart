import 'package:flutter/material.dart';

void main() => runApp(const HardwareHyperApp());

class HardwareHyperApp extends StatelessWidget {
  const HardwareHyperApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Hardware Hyper Zimbabwe',
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFFF26A21)),
        scaffoldBackgroundColor: const Color(0xFFF5F1EA),
      ),
      home: const StorePage(),
    );
  }
}

class Product {
  const Product(this.id, this.name, this.category, this.description, this.priceUsd,
      this.priceZig, this.rating, this.stock, this.delivery, this.visual);

  final int id;
  final String name;
  final String category;
  final String description;
  final double priceUsd;
  final int priceZig;
  final double rating;
  final String stock;
  final String delivery;
  final String visual;
}

const products = <Product>[
  Product(1, 'Makita 18V Cordless Drill Kit', 'Power Tools',
      'Brushless drill with batteries, charger, and contractor case.', 189, 5103, 4.8, 'In Stock', 'Harare same day', 'DRILL'),
  Product(2, 'RapidSet Portland Cement 50kg', 'Building Materials',
      'Reliable cement for slabs, walls, and structural work.', 14, 378, 4.6, 'Bulk Ready', 'Nationwide delivery', 'CEMENT'),
  Product(3, 'PEX Plumbing Starter Bundle', 'Plumbing Supplies',
      'Pipes, fittings, tape, and pressure connectors.', 74, 1998, 4.5, 'In Stock', 'Harare next day', 'PIPES'),
  Product(4, 'Industrial Extension Reel 30m', 'Electrical Equipment',
      'Heavy-duty outdoor cable reel for jobsite power.', 59, 1593, 4.7, 'Low Stock', 'Bulawayo 2 days', 'REEL'),
  Product(5, 'WeatherShield Roof Sheet Pack', 'Roofing Materials',
      'Roof sheets with fasteners and ridge cap options.', 248, 6696, 4.9, 'In Stock', 'Project delivery', 'ROOF'),
  Product(6, 'ProGuard Safety PPE Set', 'Safety Equipment',
      'Helmet, gloves, goggles, masks, and reflective vest.', 36, 972, 4.4, 'In Stock', 'Ready for pickup', 'PPE'),
];

class StorePage extends StatefulWidget {
  const StorePage({super.key});

  @override
  State<StorePage> createState() => _StorePageState();
}

class _StorePageState extends State<StorePage> {
  final searchController = TextEditingController();
  final cart = <int, int>{};
  final wishlist = <int>{};
  String category = 'All';
  bool wishlistOnly = false;

  List<String> get categories => ['All', ...products.map((e) => e.category).toSet()];

  List<Product> get visibleProducts {
    final query = searchController.text.trim().toLowerCase();
    return products.where((product) {
      if (category != 'All' && product.category != category) return false;
      if (wishlistOnly && !wishlist.contains(product.id)) return false;
      if (query.isEmpty) return true;
      final haystack = '${product.name} ${product.category} ${product.description}'.toLowerCase();
      return haystack.contains(query);
    }).toList();
  }

  int get cartCount => cart.values.fold(0, (sum, value) => sum + value);

  double get subtotal => cart.entries.fold(0, (sum, entry) {
        final product = products.firstWhere((item) => item.id == entry.key);
        return sum + product.priceUsd * entry.value;
      });

  void addToCart(int id) => setState(() => cart.update(id, (value) => value + 1, ifAbsent: () => 1));

  void changeQty(int id, int delta) {
    setState(() {
      final current = cart[id];
      if (current == null) return;
      final next = current + delta;
      if (next <= 0) {
        cart.remove(id);
      } else {
        cart[id] = next;
      }
    });
  }

  void toggleWishlist(int id) {
    setState(() {
      if (wishlist.contains(id)) {
        wishlist.remove(id);
      } else {
        wishlist.add(id);
      }
      if (wishlistOnly && wishlist.isEmpty) wishlistOnly = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    final columns = width >= 1200 ? 3 : width >= 760 ? 2 : 1;

    return Scaffold(
      endDrawer: Drawer(
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Your cart', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800)),
                const SizedBox(height: 16),
                Expanded(
                  child: cart.isEmpty
                      ? const Center(child: Text('Your cart is empty.'))
                      : ListView(
                          children: cart.entries.map((entry) {
                            final product = products.firstWhere((item) => item.id == entry.key);
                            return Card(
                              child: Padding(
                                padding: const EdgeInsets.all(12),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(product.name, style: const TextStyle(fontWeight: FontWeight.w800)),
                                    const SizedBox(height: 8),
                                    Row(
                                      children: [
                                        Expanded(child: Text(product.delivery)),
                                        IconButton(onPressed: () => changeQty(product.id, -1), icon: const Icon(Icons.remove)),
                                        Text('${entry.value}'),
                                        IconButton(onPressed: () => changeQty(product.id, 1), icon: const Icon(Icons.add)),
                                      ],
                                    )
                                  ],
                                ),
                              ),
                            );
                          }).toList(),
                        ),
                ),
                Text('Subtotal: \$${subtotal.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.w800)),
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: () {},
                  style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48), backgroundColor: const Color(0xFFF26A21)),
                  child: const Text('Proceed to checkout'),
                ),
              ],
            ),
          ),
        ),
      ),
      body: Builder(
        builder: (context) => SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1380),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(18),
                      decoration: panelDecoration(),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const CircleAvatar(
                                radius: 28,
                                backgroundColor: Color(0xFFF26A21),
                                child: Text('HH', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800)),
                              ),
                              const SizedBox(width: 14),
                              const Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text('BUILT FOR ZIMBABWE', style: TextStyle(color: Color(0xFFCB4E0D), fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 1.5)),
                                    Text('Hardware Hyper', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
                                  ],
                                ),
                              ),
                              FilledButton.tonal(
                                onPressed: () => setState(() => wishlistOnly = !wishlistOnly),
                                style: FilledButton.styleFrom(
                                  backgroundColor: wishlistOnly ? const Color(0xFF111111) : null,
                                  foregroundColor: wishlistOnly ? Colors.white : null,
                                ),
                                child: Text('Wishlist ${wishlist.length}'),
                              ),
                              const SizedBox(width: 10),
                              FilledButton(
                                onPressed: () => Scaffold.of(context).openEndDrawer(),
                                style: FilledButton.styleFrom(backgroundColor: const Color(0xFFF26A21)),
                                child: Text('Cart $cartCount'),
                              ),
                            ],
                          ),
                          const SizedBox(height: 16),
                          TextField(
                            controller: searchController,
                            onChanged: (_) => setState(() {}),
                            decoration: inputDecoration('Search tools, cement, paint, plumbing, roofing...'),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(28),
                      decoration: panelDecoration(),
                      child: const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('CONTRACTOR-GRADE MARKETPLACE', style: TextStyle(color: Color(0xFFCB4E0D), fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 1.5)),
                          SizedBox(height: 8),
                          Text('Everything for the next build, repair, and renovation.', style: TextStyle(fontSize: 42, fontWeight: FontWeight.w800, height: 0.95)),
                          SizedBox(height: 14),
                          Text('Shop power tools, building materials, plumbing supplies, and electrical equipment with local delivery, click-and-collect, and Zimbabwe-friendly checkout options.', style: TextStyle(color: Color(0xFF666057), height: 1.5)),
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),
                    Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: categories.map((item) {
                        final active = item == category;
                        return ChoiceChip(
                          label: Text(item),
                          selected: active,
                          onSelected: (_) => setState(() => category = item),
                          selectedColor: const Color(0xFF111111),
                          labelStyle: TextStyle(color: active ? Colors.white : const Color(0xFF1D1D1D)),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 18),
                    Container(
                      padding: const EdgeInsets.all(24),
                      decoration: panelDecoration(),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Expanded(child: Text('Featured hardware products', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800))),
                              Text('${visibleProducts.length} products', style: const TextStyle(color: Color(0xFF666057))),
                            ],
                          ),
                          const SizedBox(height: 20),
                          GridView.builder(
                            itemCount: visibleProducts.length,
                            shrinkWrap: true,
                            physics: const NeverScrollableScrollPhysics(),
                            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: columns,
                              crossAxisSpacing: 16,
                              mainAxisSpacing: 16,
                              childAspectRatio: 0.72,
                            ),
                            itemBuilder: (context, index) {
                              final product = visibleProducts[index];
                              final wished = wishlist.contains(product.id);
                              return Container(
                                decoration: BoxDecoration(
                                  color: Colors.white,
                                  borderRadius: BorderRadius.circular(28),
                                  border: Border.all(color: const Color(0x14000000)),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Container(
                                      height: 180,
                                      padding: const EdgeInsets.all(18),
                                      decoration: const BoxDecoration(
                                        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
                                        gradient: LinearGradient(colors: [Color(0x2EF26A21), Color(0x12FFFFFF)]),
                                      ),
                                      child: Column(
                                        children: [
                                          Row(
                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                            children: [
                                              Text(product.stock, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800)),
                                              IconButton.filledTonal(
                                                onPressed: () => toggleWishlist(product.id),
                                                style: IconButton.styleFrom(
                                                  backgroundColor: wished ? const Color(0xFF111111) : Colors.white,
                                                  foregroundColor: wished ? Colors.white : const Color(0xFF111111),
                                                ),
                                                icon: Icon(wished ? Icons.close : Icons.add),
                                              ),
                                            ],
                                          ),
                                          const Spacer(),
                                          Center(child: Text(product.visual, style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w800))),
                                          const Spacer(),
                                        ],
                                      ),
                                    ),
                                    Padding(
                                      padding: const EdgeInsets.all(18),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(product.category.toUpperCase(), style: const TextStyle(color: Color(0xFF666057), fontSize: 11, fontWeight: FontWeight.w800)),
                                          const SizedBox(height: 8),
                                          Text(product.name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
                                          const SizedBox(height: 6),
                                          Text(product.description, maxLines: 3, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Color(0xFF666057))),
                                          const SizedBox(height: 14),
                                          Text('\$${product.priceUsd.toStringAsFixed(2)}  |  ZiG ${product.priceZig}', style: const TextStyle(fontWeight: FontWeight.w800)),
                                          const SizedBox(height: 8),
                                          Text('${product.rating} / 5 rating  |  ${product.delivery}', style: const TextStyle(color: Color(0xFF666057))),
                                          const SizedBox(height: 16),
                                          FilledButton(
                                            onPressed: () => addToCart(product.id),
                                            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFF26A21)),
                                            child: const Text('Add to cart'),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              );
                            },
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

InputDecoration inputDecoration(String hint) {
  return InputDecoration(
    hintText: hint,
    filled: true,
    fillColor: Colors.white,
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(18),
      borderSide: const BorderSide(color: Color(0x1A000000)),
    ),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(18),
      borderSide: const BorderSide(color: Color(0x1A000000)),
    ),
  );
}

BoxDecoration panelDecoration() {
  return BoxDecoration(
    color: Colors.white.withOpacity(0.84),
    borderRadius: BorderRadius.circular(32),
    border: Border.all(color: const Color(0x14000000)),
    boxShadow: const [
      BoxShadow(
        color: Color(0x1F1C1208),
        blurRadius: 50,
        offset: Offset(0, 20),
      ),
    ],
  );
}
