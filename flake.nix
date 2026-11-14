{
  description = "C toolchain for AV2 work (AVM, dav2d), close to VideoLAN CI";

  inputs.nixpkgs.url = "nixpkgs";

  outputs = { nixpkgs, ... }:
    let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
      llvm = pkgs.llvmPackages;
      # nixpkgs' clang wrapper links compiler-rt's sanitizer runtimes but not its
      # <sanitizer/*.h> headers, which dav2d includes in MSan builds.
      clang = llvm.clang.overrideAttrs (o: {
        postFixup = (o.postFixup or "") + ''
          echo " -idirafter ${llvm.compiler-rt.dev}/include" >> $out/nix-support/cc-cflags
        '';
      });
    in {
      # nix develop /srv/compression/projects/AV2
      # gcc by default; sanitizer builds as in CI: CC=clang meson setup ...
      devShells.x86_64-linux.default = pkgs.mkShell {
        packages = [ clang ] ++ (with pkgs; [
          meson ninja nasm cmake pkg-config perl python3
          llvm.llvm gdb rr valgrind
        ]);
        CC = "gcc";
        CXX = "g++";
        # The wrapper's default hardening (_FORTIFY_SOURCE etc.) gives MSan false
        # positives in dav2d's testdata tests; Debian CI builds without it.
        hardeningDisable = [ "all" ];
      };
    };
}
