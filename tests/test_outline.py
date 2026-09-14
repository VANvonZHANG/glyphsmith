# tests/test_outline.py
from gsrender.outline import Outline

def test_push_and_contours():
    o = Outline()
    o.new_contour()
    o.push(10, 20)
    o.push(30, 20)
    assert o.contours == [[(10.0, 20.0, 0), (30.0, 20.0, 0)]]

def test_two_contours():
    o = Outline()
    o.new_contour(); o.push(0, 0); o.push(5, 0)
    o.new_contour(); o.push(1, 1); o.push(2, 2)
    assert len(o.contours) == 2

def test_to_path_d_polyline():
    o = Outline.from_contours([[(0.0, 0.0, 0), (100.0, 0.0, 0), (100.0, 50.0, 0)]])
    d = o.to_path_d()
    assert d.startswith("M 0,0")
    assert "L 100,0" in d

def test_to_path_d_quadratic_offcurve():
    # TrueType 惯例：off 点作 Q 控制，连续 off 点间插入隐含中点
    o = Outline.from_contours([[(0.0, 0.0, 0), (50.0, 25.0, 1), (100.0, 0.0, 0)]])
    d = o.to_path_d()
    assert "Q 50,25" in d

def test_to_svg_wraps_viewbox():
    o = Outline.from_contours([[(0.0, 0.0, 0), (100.0, 0.0, 0), (100.0, 50.0, 0)]])
    svg = o.to_svg(size=200)
    assert svg.startswith("<svg") and 'viewBox="0 0 200 200"' in svg and "</svg>" in svg
