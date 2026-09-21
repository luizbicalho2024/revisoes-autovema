from __future__ import annotations

import json
import uuid
from typing import Any

import streamlit.components.v1 as components

from .appearance import normalize_appearance


AMCHARTS_BASE = "https://cdn.amcharts.com/lib/5"


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )


def _hex_value(value: str) -> str:
    return value.lstrip("#")


def _frame(body: str, chart_id: str, height: int) -> None:
    components.html(
        f"""
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            html,body{{margin:0;padding:0;background:transparent;font-family:Inter,Arial,sans-serif;}}
            #{chart_id}{{width:100%;height:{height}px;}}
          </style>
          <script src="{AMCHARTS_BASE}/index.js"></script>
          <script src="{AMCHARTS_BASE}/xy.js"></script>
          <script src="{AMCHARTS_BASE}/percent.js"></script>
          <script src="{AMCHARTS_BASE}/themes/Animated.js"></script>
        </head>
        <body>
          <div id="{chart_id}"></div>
          <script>
          am5.ready(function() {{
            {body}
          }});
          </script>
        </body>
        </html>
        """,
        height=height + 8,
        scrolling=False,
    )


def column_chart(
    data: list[dict[str, Any]],
    *,
    category_field: str,
    value_field: str,
    appearance: dict[str, Any] | None = None,
    height: int = 320,
) -> None:
    theme = normalize_appearance(appearance)
    chart_id = f"amchart_{uuid.uuid4().hex}"
    body = f"""
      var root = am5.Root.new("{chart_id}");
      root.setThemes([am5themes_Animated.new(root)]);

      var chart = root.container.children.push(am5xy.XYChart.new(root, {{
        panX:false, panY:false, wheelX:"none", wheelY:"none",
        paddingLeft:4, paddingRight:10, paddingTop:8, paddingBottom:0
      }}));

      var xRenderer = am5xy.AxisRendererX.new(root, {{ minGridDistance:30 }});
      xRenderer.grid.template.setAll({{ strokeOpacity:0 }});
      xRenderer.labels.template.setAll({{
        fill:am5.color(0x{_hex_value(theme["muted_color"])}),
        fontSize:12,
        paddingTop:10
      }});

      var xAxis = chart.xAxes.push(am5xy.CategoryAxis.new(root, {{
        categoryField:"{category_field}",
        renderer:xRenderer
      }}));

      var yRenderer = am5xy.AxisRendererY.new(root, {{}});
      yRenderer.grid.template.setAll({{
        stroke:am5.color(0x{_hex_value(theme["border_color"])}),
        strokeOpacity:.45
      }});
      yRenderer.labels.template.setAll({{
        fill:am5.color(0x{_hex_value(theme["muted_color"])}),
        fontSize:11
      }});

      var yAxis = chart.yAxes.push(am5xy.ValueAxis.new(root, {{
        min:0,
        extraMax:.12,
        renderer:yRenderer
      }}));

      var series = chart.series.push(am5xy.ColumnSeries.new(root, {{
        xAxis:xAxis,
        yAxis:yAxis,
        valueYField:"{value_field}",
        categoryXField:"{category_field}",
        fill:am5.color(0x{_hex_value(theme["primary_color"])}),
        stroke:am5.color(0x{_hex_value(theme["primary_color"])}),
        tooltip:am5.Tooltip.new(root, {{ labelText:"{{categoryX}}: {{valueY}}" }})
      }}));

      series.columns.template.setAll({{
        width:am5.percent(58),
        strokeOpacity:0,
        cornerRadiusTL:6,
        cornerRadiusTR:6,
        fillOpacity:.92
      }});

      series.bullets.push(function() {{
        return am5.Bullet.new(root, {{
          locationY:1,
          sprite:am5.Label.new(root, {{
            text:"{{valueY}}",
            centerX:am5.p50,
            centerY:am5.p100,
            dy:-8,
            fill:am5.color(0x{_hex_value(theme["text_color"])}),
            fontSize:11,
            fontWeight:"600"
          }})
        }});
      }});

      var data = {_json(data)};
      xAxis.data.setAll(data);
      series.data.setAll(data);
      series.appear(500);
      chart.appear(500,80);
    """
    _frame(body, chart_id, height)


def line_chart(
    data: list[dict[str, Any]],
    *,
    category_field: str,
    value_field: str,
    appearance: dict[str, Any] | None = None,
    height: int = 320,
) -> None:
    theme = normalize_appearance(appearance)
    chart_id = f"amchart_{uuid.uuid4().hex}"
    body = f"""
      var root = am5.Root.new("{chart_id}");
      root.setThemes([am5themes_Animated.new(root)]);

      var chart = root.container.children.push(am5xy.XYChart.new(root, {{
        panX:false, panY:false, wheelX:"none", wheelY:"none",
        paddingLeft:4, paddingRight:12, paddingTop:8, paddingBottom:0
      }}));

      var xRenderer = am5xy.AxisRendererX.new(root, {{ minGridDistance:42 }});
      xRenderer.grid.template.setAll({{ strokeOpacity:0 }});
      xRenderer.labels.template.setAll({{
        fill:am5.color(0x{_hex_value(theme["muted_color"])}),
        fontSize:11,
        paddingTop:10
      }});

      var xAxis = chart.xAxes.push(am5xy.CategoryAxis.new(root, {{
        categoryField:"{category_field}",
        renderer:xRenderer
      }}));

      var yRenderer = am5xy.AxisRendererY.new(root, {{}});
      yRenderer.grid.template.setAll({{
        stroke:am5.color(0x{_hex_value(theme["border_color"])}),
        strokeOpacity:.45
      }});
      yRenderer.labels.template.setAll({{
        fill:am5.color(0x{_hex_value(theme["muted_color"])}),
        fontSize:11
      }});

      var yAxis = chart.yAxes.push(am5xy.ValueAxis.new(root, {{
        min:0,
        renderer:yRenderer
      }}));

      var series = chart.series.push(am5xy.LineSeries.new(root, {{
        xAxis:xAxis,
        yAxis:yAxis,
        valueYField:"{value_field}",
        categoryXField:"{category_field}",
        stroke:am5.color(0x{_hex_value(theme["primary_color"])}),
        fill:am5.color(0x{_hex_value(theme["primary_color"])}),
        tooltip:am5.Tooltip.new(root, {{ labelText:"{{categoryX}}: {{valueY}}" }})
      }}));

      series.strokes.template.setAll({{ strokeWidth:2.5 }});

      series.bullets.push(function() {{
        return am5.Bullet.new(root, {{
          sprite:am5.Circle.new(root, {{
            radius:4,
            fill:am5.color(0x{_hex_value(theme["surface_color"])}),
            stroke:am5.color(0x{_hex_value(theme["primary_color"])}),
            strokeWidth:2
          }})
        }});
      }});

      var cursor = chart.set("cursor", am5xy.XYCursor.new(root, {{
        behavior:"none"
      }}));
      cursor.lineY.set("visible", false);
      cursor.lineX.setAll({{
        stroke:am5.color(0x{_hex_value(theme["border_color"])}),
        strokeOpacity:.8
      }});

      var data = {_json(data)};
      xAxis.data.setAll(data);
      series.data.setAll(data);
      series.appear(500);
      chart.appear(500,80);
    """
    _frame(body, chart_id, height)


def donut_chart(
    data: list[dict[str, Any]],
    *,
    category_field: str,
    value_field: str,
    appearance: dict[str, Any] | None = None,
    height: int = 300,
) -> None:
    theme = normalize_appearance(appearance)
    chart_id = f"amchart_{uuid.uuid4().hex}"

    palette = [
        theme["primary_color"],
        theme["secondary_color"],
        theme["accent_color"],
        "#64748B",
        "#94A3B8",
        "#CBD5E1",
    ]
    colors = ",".join(f"am5.color(0x{_hex_value(c)})" for c in palette)

    body = f"""
      var root = am5.Root.new("{chart_id}");
      root.setThemes([am5themes_Animated.new(root)]);

      var chart = root.container.children.push(am5percent.PieChart.new(root, {{
        innerRadius:am5.percent(66),
        layout:root.horizontalLayout
      }}));

      var series = chart.series.push(am5percent.PieSeries.new(root, {{
        valueField:"{value_field}",
        categoryField:"{category_field}",
        alignLabels:false
      }}));

      series.set("colors", am5.ColorSet.new(root, {{
        colors:[{colors}],
        reuse:true
      }}));

      series.slices.template.setAll({{
        stroke:am5.color(0x{_hex_value(theme["surface_color"])}),
        strokeWidth:3,
        tooltipText:"{{category}}: {{value}}"
      }});
      series.labels.template.set("forceHidden", true);
      series.ticks.template.set("forceHidden", true);

      var legend = chart.children.push(am5.Legend.new(root, {{
        centerY:am5.p50,
        y:am5.p50,
        layout:root.verticalLayout
      }}));
      legend.labels.template.setAll({{
        fill:am5.color(0x{_hex_value(theme["text_color"])}),
        fontSize:11
      }});
      legend.valueLabels.template.setAll({{
        fill:am5.color(0x{_hex_value(theme["muted_color"])}),
        fontSize:11
      }});

      var data = {_json(data)};
      series.data.setAll(data);
      legend.data.setAll(series.dataItems);
      series.appear(500,80);
    """
    _frame(body, chart_id, height)
