class Qdex < Formula
  desc "Keyboard-first neon terminal file and app launcher for macOS"
  homepage "https://ard-tube.github.io/qdex/"
  url "https://github.com/ard-tube/qdex/releases/download/v1.0.0/qdex-v1.0.0.tar.gz"
  sha256 "e3d3ac1842e85a5f67bf12b641814fa8abb0b4b6b59b5b31a3a8b27bcfd61161"
  license "MIT"

  depends_on :macos
  depends_on "python@3.13"

  def install
    bin.install "qdex.py" => "qdex"
    chmod 0755, bin/"qdex"
  end

  test do
    assert_match "keyboard-first neon terminal launcher", shell_output("#{bin}/qdex --help")
  end
end
