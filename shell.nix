{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = [
    pkgs.freecad
  ];

  shellHook = ''
    echo "FreeCAD environment ready."
    echo "  - GUI:        freecad"
    echo "  - Verify:     freecadcmd -c \"exec(open('verify_fixture.py').read())\""
    echo "  - Export:     freecadcmd -c \"exec(open('export_qdn.py').read())\""
  '';
}