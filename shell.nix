{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = [
    pkgs.freecad
  ];

  shellHook = ''
    echo "FreeCAD environment ready."
    echo "  - GUI:        freecad"
    echo "  - Headless:   freecadcmd --console verify_fixture.py"
  '';
}