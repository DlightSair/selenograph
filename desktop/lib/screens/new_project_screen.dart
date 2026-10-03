import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;

import '../services/algo_paths.dart';
import '../services/api_client.dart';
import '../theme/platinum.dart';
import '../ui/controls.dart';
import '../ui/panels.dart';
import '../ui/screen.dart';

/// Pointing the pipeline at a new area means a lat/lon box plus the paths to
/// an already-downloaded PDS4 source product and reference mosaic — there is
/// no generic "pick any picture" flow because the pipeline only understands
/// PDS4-labeled Chandrayaan-2 products (see algo/src/algo/utils/io.py). This
/// form writes a real configs/<name>.yaml via POST /configs, validated
/// server-side (paths must actually exist).
class NewProjectScreen extends StatefulWidget {
  final ApiClient api;

  const NewProjectScreen({super.key, required this.api});

  @override
  State<NewProjectScreen> createState() => _NewProjectScreenState();
}

class _NewProjectScreenState extends State<NewProjectScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _aoiNameCtrl = TextEditingController();
  final _latMinCtrl = TextEditingController();
  final _latMaxCtrl = TextEditingController();
  final _lonMinCtrl = TextEditingController();
  final _lonMaxCtrl = TextEditingController();
  final _sourcePathCtrl = TextEditingController();
  final _referencePathCtrl = TextEditingController();
  final _demPathCtrl = TextEditingController();

  String _instrument = 'TMC2';
  bool _demEnabled = false;
  bool _submitting = false;
  String? _error;

  @override
  void dispose() {
    for (final c in [
      _nameCtrl,
      _aoiNameCtrl,
      _latMinCtrl,
      _latMaxCtrl,
      _lonMinCtrl,
      _lonMaxCtrl,
      _sourcePathCtrl,
      _referencePathCtrl,
      _demPathCtrl,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  String? _required(String v) => v.isEmpty ? 'Required' : null;

  String? _number(String v) {
    if (v.isEmpty) return 'Required';
    if (double.tryParse(v) == null) return 'Must be a number';
    return null;
  }

  /// Converts an absolute path from the OS picker into one relative to algo/,
  /// matching the convention every existing configs/*.yaml uses (e.g.
  /// "../data/raw/..."). Falls back to the absolute path if algo/ can't be
  /// located — the server accepts that too, it just won't match the house
  /// style or survive moving the project to another machine.
  String _toConfigRelativePath(String absolutePath) {
    final algoDir = AlgoPaths.findAlgoDir();
    if (algoDir == null) return absolutePath;
    return p.relative(absolutePath, from: algoDir.path).replaceAll('\\', '/');
  }

  Future<void> _pickDirectory(TextEditingController controller) async {
    final path = await getDirectoryPath(confirmButtonText: 'Select folder');
    if (path == null) return;
    setState(() => controller.text = _toConfigRelativePath(path));
  }

  /// Fills the AOI from the source product's own footprint (whole product;
  /// narrow it by editing the fields).
  Future<void> _fillFromSource() async {
    final path = _sourcePathCtrl.text.trim();
    if (path.isEmpty) {
      setState(() => _error = 'Set the source folder first.');
      return;
    }
    try {
      final b = await widget.api.getFootprint(path);
      if (!mounted) return;
      setState(() {
        _error = null;
        _latMinCtrl.text = b[0].toStringAsFixed(4);
        _latMaxCtrl.text = b[1].toStringAsFixed(4);
        _lonMinCtrl.text = b[2].toStringAsFixed(4);
        _lonMaxCtrl.text = b[3].toStringAsFixed(4);
      });
    } catch (e) {
      if (mounted) setState(() => _error = 'Footprint unavailable: $e');
    }
  }

  Future<void> _pickFile(TextEditingController controller) async {
    const typeGroup = XTypeGroup(label: 'GeoTIFF', extensions: ['tif', 'tiff']);
    final file = await openFile(acceptedTypeGroups: [typeGroup]);
    if (file == null) return;
    setState(() => controller.text = _toConfigRelativePath(file.path));
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.api.createConfig(
        name: _nameCtrl.text.trim(),
        aoiName: _aoiNameCtrl.text.trim(),
        latMin: double.parse(_latMinCtrl.text.trim()),
        latMax: double.parse(_latMaxCtrl.text.trim()),
        lonMin: double.parse(_lonMinCtrl.text.trim()),
        lonMax: double.parse(_lonMaxCtrl.text.trim()),
        sourceInstrument: _instrument,
        sourcePath: _sourcePathCtrl.text.trim(),
        referencePath: _referencePathCtrl.text.trim(),
        demEnabled: _demEnabled,
        demPath: _demEnabled ? _demPathCtrl.text.trim() : null,
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ScreenHeader(
          title: 'New project',
          subtitle: 'Writes a project file the pipeline can run',
          showBack: true,
          onBack: () => Navigator.of(context).pop(false),
        ),
        Expanded(
          child: ScreenBody(
            maxWidth: 780,
            child: Entrance(child: _form()),
          ),
        ),
      ],
    );
  }

  Widget _form() {
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          GroupBox(
            title: 'Project',
            child: Column(
              children: [
                _row('Name', PtTextField(controller: _nameCtrl, validator: _required, hint: 'aristarchus'), hint: 'Used as the file name of the project.'),
                const SizedBox(height: 10),
                _row('Area name', PtTextField(controller: _aoiNameCtrl, validator: _required, hint: 'aristarchus_plateau'), hint: 'Shown as the project title.'),
              ],
            ),
          ),
          const SizedBox(height: 16),
          GroupBox(
            title: 'Area of interest (degrees)',
            child: Column(
              children: [
                Align(
                  alignment: Alignment.centerRight,
                  child: PushButton(label: 'Fill from source', onPressed: _fillFromSource, compact: true),
                ),
                const SizedBox(height: 8),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _row('Latitude min', _num(_latMinCtrl), labelWidth: 100)),
                    const SizedBox(width: 18),
                    Expanded(child: _row('Latitude max', _num(_latMaxCtrl), labelWidth: 100)),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _row('Longitude min', _num(_lonMinCtrl), labelWidth: 100)),
                    const SizedBox(width: 18),
                    Expanded(child: _row('Longitude max', _num(_lonMaxCtrl), labelWidth: 100)),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          GroupBox(
            title: 'Imagery',
            child: Column(
              children: [
                _row(
                  'Instrument',
                  Align(
                    alignment: Alignment.centerLeft,
                    child: PtPopup<String>(
                      value: _instrument,
                      items: const ['TMC2', 'OHRC', 'IIRS'],
                      width: 140,
                      onChanged: (v) => setState(() => _instrument = v),
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                _row(
                  'Source',
                  _withBrowse(PtTextField(controller: _sourcePathCtrl, validator: _required, hint: '../data/raw/chandrayaan2/tmc2/<product>'), () => _pickDirectory(_sourcePathCtrl)),
                  hint: 'PDS4 product folder. Pick it first, then use Fill from source under AOI.',
                ),
                const SizedBox(height: 10),
                _row(
                  'Reference',
                  _withBrowse(PtTextField(controller: _referencePathCtrl, validator: _required, hint: '../data/raw/lro_reference/<area>/nac/<file>.TIF'), () => _pickFile(_referencePathCtrl)),
                  hint: 'The reference GeoTIFF.',
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          GroupBox(
            title: 'Elevation model',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                PtCheckbox(
                  value: _demEnabled,
                  label: 'Use a DEM',
                  hint: 'Lets the pipeline relight the terrain with the source image’s Sun and model terrain parallax.',
                  onChanged: (v) => setState(() => _demEnabled = v),
                ),
                AnimatedSize(
                  duration: const Duration(milliseconds: 260),
                  curve: Curves.easeOutCubic,
                  alignment: Alignment.topCenter,
                  child: _demEnabled
                      ? Padding(
                          padding: const EdgeInsets.only(top: 10),
                          child: _row(
                            'DEM',
                            _withBrowse(PtTextField(controller: _demPathCtrl, validator: _required, hint: '../data/dem/<area>/<file>.tif'), () => _pickFile(_demPathCtrl)),
                            hint: 'The DEM GeoTIFF.',
                          ),
                        )
                      : const SizedBox(width: double.infinity),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          if (_error != null) ...[
            Callout(kind: CalloutKind.error, title: 'Could not create the project', child: SelectableText(_error!, style: ui(size: 11.5))),
            const SizedBox(height: 12),
          ],
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              PushButton(label: 'Cancel', onPressed: _submitting ? null : () => Navigator.of(context).pop(false)),
              const SizedBox(width: 10),
              PushButton(label: _submitting ? 'Creating…' : 'Create project', isDefault: true, onPressed: _submitting ? null : _submit),
            ],
          ),
        ],
      ),
    );
  }

  Widget _num(TextEditingController c) => PtTextField(
        controller: c,
        validator: _number,
        keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
      );

  Widget _withBrowse(Widget field, VoidCallback onBrowse) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(child: field),
          const SizedBox(width: 8),
          PushButton(label: 'Browse…', onPressed: onBrowse, compact: true),
        ],
      );

  /// Classic dialog row: right-aligned label, then the control, then an
  /// optional hint line.
  Widget _row(String label, Widget field, {String? hint, double labelWidth = 92}) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: labelWidth,
          child: Padding(
            padding: const EdgeInsets.only(top: 5, right: 10),
            child: Text(label, textAlign: TextAlign.right, style: ui()),
          ),
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              field,
              if (hint != null)
                Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Text(hint, style: captionStyle()),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
