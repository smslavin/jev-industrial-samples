"""A tiny simulated galaxy: the tag catalog the router can select from, with live values.

In a real deployment the catalog comes from graccess-mcp (objects, templates, areas,
descriptions) and the values from MxAccess.
"""

CATALOG = {
    "TIC_101": {"template": "$PIDController", "area": "Reactor_R100", "description": "Reactor R-100 jacket temperature controller", "units": "degC",
                "values": {"PV": 79.6, "SP": 80.0, "Mode": "Auto", "Alarm": "Normal"}},
    "LT_200": {"template": "$LevelTransmitter", "area": "TankFarm", "description": "Caustic storage tank T-200 level", "units": "%",
               "values": {"PV": 62.4, "Alarm": "Normal"}},
    "P_301": {"template": "$Pump", "area": "Utilities", "description": "Cooling water supply pump P-301 (duty)", "units": "",
              "values": {"Status": "Running", "Mode": "Auto", "Alarm": "Normal"}},
    "P_302": {"template": "$Pump", "area": "Utilities", "description": "Cooling water supply pump P-302 (standby)", "units": "",
              "values": {"Status": "Out of service", "Mode": "Manual", "Alarm": "Normal"}},
    "FT_110": {"template": "$FlowTransmitter", "area": "Intake", "description": "Raw water inflow", "units": "m3/h",
               "values": {"PV": 412.0, "Alarm": "Normal"}},
    "LSLL_400": {"template": "$TripFunction", "area": "Boiler_B400", "description": "Boiler B-400 drum low-low level trip", "units": "%",
                 "values": {"PV": 48.0, "SP": 25.0, "Alarm": "Normal"}},
    "PT_410": {"template": "$PressureTransmitter", "area": "Boiler_B400", "description": "Boiler B-400 drum pressure", "units": "barg",
               "values": {"PV": 18.2, "Alarm": "Normal"}},
    "P_510": {"template": "$DosingPump", "area": "Disinfection", "description": "Sodium hypochlorite dosing pump P-510", "units": "",
              "values": {"Status": "Running", "Mode": "Auto", "Alarm": "Normal"}},
    "AIT_520": {"template": "$Analyzer", "area": "Disinfection", "description": "Free chlorine residual, treated water", "units": "mg/L",
                "values": {"PV": 0.82, "Alarm": "Normal"}},
    "M_220": {"template": "$VFDMotor", "area": "Blending", "description": "Blend tank mixer M-220", "units": "%",
              "values": {"PV": 74.8, "SP": 75.0, "Status": "Running", "Mode": "Auto", "Alarm": "Normal"}},
}
