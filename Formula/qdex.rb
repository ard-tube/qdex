class Qdex < Formula
  desc "Keyboard-first neon terminal file and app launcher for macOS"
  homepage "https://ard-tube.github.io/qdex/"
  url "https://github.com/ard-tube/qdex/releases/download/v1.0.0/qdex-v1.0.0.tar.gz"
  sha256 "fba3580d75a766559c71f82fe48346b111ef9869890f6c651c48e4aed6a14afe"
  license "MIT"

  depends_on :macos
  depends_on "python@3.13"

  def install
    libexec.install "qdex.py"
    python = Formula["python@3.13"].opt_bin/"python3.13"
    (bin/"qdex").write <<~SH
      #!/bin/sh
      exec "#{python}" "#{libexec}/qdex.py" "$@"
    SH
    chmod 0755, bin/"qdex"
  end

  test do
    assert_match "keyboard-first neon terminal launcher", shell_output("#{bin}/qdex --help")
  end
end
