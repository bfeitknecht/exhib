{
  # The tools for this repository: `nix develop`, or direnv (`.envrc`).
  description = "exhib: the exhibition site (Hugo, Python tool)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        "aarch64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      forAllSystems =
        f:
        nixpkgs.lib.genAttrs systems (
          system:
          f (
            import nixpkgs {
              inherit system;
            }
          )
        );
    in
    {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShellNoCC {
          packages = [
            pkgs.hugo
            pkgs.uv
            pkgs.python3
            pkgs.kubectl
            pkgs.just
          ];
        };
      });
      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
