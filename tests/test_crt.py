from nostalgiabox.config import CrtConfig
from nostalgiabox.crt import render_shader, write_shader


def test_shader_contains_baked_constants():
    crt = CrtConfig(curvature=0.15, corner_radius=0.05, vignette=0.3, scanlines=True)
    shader = render_shader(crt)
    assert "//!HOOK MAIN" in shader
    assert "0.15000" in shader          # curvature baked in
    assert "#define SCANLINES 1" in shader


def test_shader_scanlines_off():
    shader = render_shader(CrtConfig(scanlines=False))
    assert "#define SCANLINES 0" in shader


def test_write_shader_disabled_returns_none(tmp_path):
    assert write_shader(CrtConfig(enabled=False), tmp_path / "crt.glsl") is None


def test_write_shader_writes_file(tmp_path):
    out = tmp_path / "crt.glsl"
    result = write_shader(CrtConfig(enabled=True), out)
    assert result == out
    assert out.is_file()
    assert "HOOK MAIN" in out.read_text()
