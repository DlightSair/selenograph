import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'package:flutter/material.dart';

import '../theme/platinum.dart';
import '../ui/controls.dart';
import '../ui/panels.dart';
import '../ui/screen.dart';

const Color _kViewerBg = Color(0xFF26262A);

/// Inline wells are a mid grey so both white plots and black overlays sit on
/// it without a jarring letterbox.
const Color _kWellBg = Color(0xFFA9A7A0);

/// A fixed-size, STATIC image well — no inline pan/zoom. An inline
/// InteractiveViewer fights the page's own scroll (drag-to-pan grabs the same
/// gesture a scroll would), so zooming only happens in the viewer window opened
/// on click, where nothing else competes for the gesture.
class ZoomableImage extends StatefulWidget {
  final String url;
  final String title;
  final double height;
  final VoidCallback? onRetry;

  const ZoomableImage({
    super.key,
    required this.url,
    required this.title,
    this.height = 200,
    this.onRetry,
  });

  @override
  State<ZoomableImage> createState() => _ZoomableImageState();
}

class _ZoomableImageState extends State<ZoomableImage> {
  bool _hovering = false;

  void _openViewer() {
    showGeneralDialog<void>(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'Close viewer',
      barrierColor: Colors.black.withValues(alpha: 0.45),
      transitionDuration: const Duration(milliseconds: 340),
      pageBuilder: (_, __, ___) => _ViewerWindow(url: widget.url, title: widget.title),
      transitionBuilder: (context, animation, secondary, child) {
        final spring = CurvedAnimation(parent: animation, curve: kSpring, reverseCurve: Curves.easeIn);
        return FadeTransition(
          opacity: CurvedAnimation(parent: animation, curve: Curves.easeOut),
          child: ScaleTransition(scale: Tween<double>(begin: 0.92, end: 1).animate(spring), child: child),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      cursor: SystemMouseCursors.zoomIn,
      onEnter: (_) => setState(() => _hovering = true),
      onExit: (_) => setState(() => _hovering = false),
      child: GestureDetector(
        onTap: _openViewer,
        child: Well(
          color: _kWellBg,
          child: SizedBox(
            height: widget.height,
            width: double.infinity,
            child: Stack(
              fit: StackFit.expand,
              children: [
                Image.network(
                  widget.url,
                  fit: BoxFit.contain,
                  loadingBuilder: (context, child, progress) {
                    if (progress == null) return child;
                    return const Center(child: Spinner(size: 22));
                  },
                  errorBuilder: (context, error, stackTrace) => Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text('Image unavailable', style: ui(color: Pt.ink, weight: FontWeight.w700)),
                        if (widget.onRetry != null) ...[
                          const SizedBox(height: 8),
                          PushButton(label: 'Retry', onPressed: widget.onRetry, compact: true),
                        ],
                      ],
                    ),
                  ),
                ),
                Positioned(
                  right: 8,
                  bottom: 8,
                  child: AnimatedOpacity(
                    duration: kFast,
                    opacity: _hovering ? 1 : 0,
                    child: IgnorePointer(
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.65),
                          borderRadius: BorderRadius.circular(kRadius),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(CupertinoIcons.zoom_in, size: 14, color: Colors.white),
                            const SizedBox(width: 5),
                            Text('Click to zoom', style: ui(size: 11, color: Colors.white)),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The zoom window: a classic titled window with a close box, a dark canvas
/// you can zoom and pan, and a small control strip.
class _ViewerWindow extends StatefulWidget {
  final String url;
  final String title;

  const _ViewerWindow({required this.url, required this.title});

  @override
  State<_ViewerWindow> createState() => _ViewerWindowState();
}

class _ViewerWindowState extends State<_ViewerWindow> {
  final TransformationController _controller = TransformationController();
  Size _viewport = Size.zero;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _zoomBy(double factor) {
    final current = _controller.value.getMaxScaleOnAxis();
    final target = (current * factor).clamp(1.0, 16.0);
    final f = target / current;
    final c = Offset(_viewport.width / 2, _viewport.height / 2);
    final m = Matrix4.translationValues(c.dx, c.dy, 0) *
        Matrix4.diagonal3Values(f, f, 1) *
        Matrix4.translationValues(-c.dx, -c.dy, 0);
    _controller.value = m * _controller.value;
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    return Center(
      child: Material(
        type: MaterialType.transparency,
        child: Container(
          width: size.width * 0.94,
          height: size.height * 0.92,
          decoration: BoxDecoration(
            color: Pt.chrome,
            borderRadius: BorderRadius.circular(kRadius + 2),
            border: Border.all(color: Pt.edge),
            boxShadow: const [BoxShadow(color: Color(0x80000000), offset: Offset(4, 5), blurRadius: 0)],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(kRadius + 1),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _titleBar(context),
                Expanded(
                  child: Container(
                    color: _kViewerBg,
                    child: LayoutBuilder(builder: (context, box) {
                      _viewport = box.biggest;
                      return InteractiveViewer(
                        transformationController: _controller,
                        minScale: 1,
                        maxScale: 16,
                        child: SizedBox.expand(
                          child: Image.network(
                            widget.url,
                            fit: BoxFit.contain,
                            filterQuality: FilterQuality.medium,
                            loadingBuilder: (context, child, progress) {
                              if (progress == null) return child;
                              return const Center(child: Spinner(size: 26));
                            },
                          ),
                        ),
                      );
                    }),
                  ),
                ),
                _controlStrip(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _titleBar(BuildContext context) {
    return Container(
      height: 28,
      decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Pt.edge))),
      child: CustomPaint(
        painter: const PinstripePainter(),
        child: Row(
          children: [
            const SizedBox(width: 8),
            _CloseBox(onTap: () => Navigator.of(context).pop()),
            const Spacer(),
            Container(
              color: Pt.chrome,
              padding: const EdgeInsets.symmetric(horizontal: 10),
              child: Text(widget.title, style: ui(weight: FontWeight.w700), maxLines: 1, overflow: TextOverflow.ellipsis),
            ),
            const Spacer(),
            const SizedBox(width: 29),
          ],
        ),
      ),
    );
  }

  Widget _controlStrip() {
    return Container(
      height: 34,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: const BoxDecoration(
        gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Pt.chromeHi, Pt.chromeLo]),
        border: Border(top: BorderSide(color: Pt.edge)),
      ),
      child: Row(
        children: [
          ToolButton(icon: CupertinoIcons.zoom_out, tooltip: 'Zoom out', onPressed: () => _zoomBy(1 / 1.6)),
          ToolButton(icon: CupertinoIcons.zoom_in, tooltip: 'Zoom in', onPressed: () => _zoomBy(1.6)),
          const SizedBox(width: 6),
          const ToolSeparator(),
          const SizedBox(width: 6),
          ToolButton(icon: CupertinoIcons.fullscreen, label: 'Fit', onPressed: () => _controller.value = Matrix4.identity()),
          const Spacer(),
          Text('Scroll or pinch to zoom · drag to pan · Esc to close', style: captionStyle()),
        ],
      ),
    );
  }
}

/// Classic square close box in a window title bar.
class _CloseBox extends StatelessWidget {
  final VoidCallback onTap;
  const _CloseBox({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return PtPressable(
      onPressed: onTap,
      tooltip: 'Close',
      builder: (context, hover, down, focus) => Container(
        width: 14,
        height: 14,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(2),
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: down ? const [Pt.chromeLo, Pt.chromeLo] : const [Pt.hi, Pt.chromeLo],
          ),
          border: Border.all(color: Pt.edge),
        ),
        child: AnimatedOpacity(
          duration: kFast,
          opacity: hover ? 1 : 0,
          child: const Icon(Icons.close, size: 11, color: Pt.ink),
        ),
      ),
    );
  }
}
