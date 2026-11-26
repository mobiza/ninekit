import 'package:flutter/material.dart';

import 'demo_page.dart';

void main() => runApp(const DemoApp());

class DemoApp extends StatelessWidget {
  const DemoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'ninekit demo',
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        backgroundColor: DemoPage.background,
        body: Center(child: SingleChildScrollView(child: DemoPage())),
      ),
    );
  }
}
