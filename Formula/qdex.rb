class Qdex < Formula
  desc "Keyboard-first neon terminal file and app launcher for macOS"
  homepage "https://ard-tube.github.io/qdex/"
  url "https://github.com/ard-tube/qdex/releases/download/v1.0.0/qdex-v1.0.0.tar.gz"
  sha256 "ac5cb33174414d159a7386a9c778eb976824178eca850d32570167c6a9ca427a"
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
