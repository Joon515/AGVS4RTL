"""PPA Estimator for Performance, Power, and Area analysis.

This module provides rule-based estimation of PPA metrics for HDL designs
based on module hierarchy, interface specifications, and constraints.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


class PPAEstimator:
    """Rule-based PPA (Performance, Power, Area) estimator."""
    
    # Technology parameters (28nm baseline)
    TECH_PARAMS = {
        "28nm": {
            "gate_delay_ps": 50,      # Gate delay in picoseconds
            "ff_area_ge": 5,          # Flip-flop area in gate equivalents
            "lut_area_ge": 6,         # LUT area in gate equivalents
            "nand2_area_ge": 1,       # 2-input NAND gate area
            "dynamic_power_pj_per_switch": 1.5,  # Dynamic power per switch
            "leakage_power_nw_per_ge": 10,  # Leakage power per gate
            "voltage": 1.2,           # Supply voltage
        }
    }
    
    # Module type complexity factors
    MODULE_COMPLEXITY = {
        "axi_slave": {"gates": 800, "ffs": 64, "freq_factor": 1.0},
        "axi_master": {"gates": 1200, "ffs": 96, "freq_factor": 0.9},
        "axi_interconnect": {"gates": 2000, "ffs": 128, "freq_factor": 0.85},
        "fifo": {"gates": 500, "ffs": 256, "freq_factor": 1.2},
        "register_file": {"gates": 300, "ffs": 512, "freq_factor": 1.5},
        "uart": {"gates": 400, "ffs": 32, "freq_factor": 1.3},
        "spi": {"gates": 350, "ffs": 24, "freq_factor": 1.4},
        "pipeline": {"gates": 200, "ffs": 64, "freq_factor": 1.8},
        "default": {"gates": 500, "ffs": 64, "freq_factor": 1.0},
    }
    
    def __init__(self, technology: str = "28nm"):
        """Initialize PPA estimator.
        
        Args:
            technology: Technology node ("28nm", "7nm", etc.)
        """
        self.technology = technology
        self.tech_params = self.TECH_PARAMS.get(technology, self.TECH_PARAMS["28nm"])
    
    def estimate(
        self,
        architecture: Dict[str, Any],
        constraints: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Estimate PPA for given architecture.
        
        Args:
            architecture: Module hierarchy from Architect Agent
            constraints: Design constraints (frequency, area budget, etc.)
        
        Returns:
            PPA report dictionary
        """
        # Extract target frequency from constraints
        target_freq_mhz = self._extract_target_frequency(constraints)
        
        # Estimate area
        area = self._estimate_area(architecture)
        
        # Estimate timing
        timing = self._estimate_timing(architecture, area, target_freq_mhz)
        
        # Estimate power
        power = self._estimate_power(area, timing)
        
        # Assess feasibility
        feasibility, warnings = self._assess_feasibility(
            area, timing, power, constraints
        )
        
        # Build report
        report = {
            "version": 1,
            "estimated_at": datetime.now(timezone.utc).isoformat(),
            "estimator": "rule_based_v1",
            "area": area,
            "power": power,
            "timing": timing,
            "feasibility": feasibility,
            "warnings": warnings,
            "metadata": {
                "architecture_version": architecture.get("version", 1),
                "technology": self.technology,
                "constraint_summary": {
                    "freq_target_mhz": target_freq_mhz,
                    "area_budget_gates": self._extract_area_budget(constraints),
                    "power_budget_mw": self._extract_power_budget(constraints),
                },
                "estimation_method": "analytical",
                "confidence": 0.75,
            }
        }
        
        return report
    
    def _extract_target_frequency(
        self,
        constraints: Dict[str, List[Dict[str, Any]]],
    ) -> float:
        """Extract target frequency from constraints.
        
        Args:
            constraints: Design constraints
        
        Returns:
            Target frequency in MHz (default 200 if not specified)
        """
        for constraint in constraints.get("hard", []):
            if constraint["name"] == "freq":
                value = constraint["value"]
                if isinstance(value, str):
                    # Parse "200MHz" format
                    import re
                    match = re.search(r"(\d+)", value)
                    if match:
                        return float(match.group(1))
                elif isinstance(value, (int, float)):
                    return float(value)
        
        return 200.0  # Default 200 MHz
    
    def _extract_area_budget(
        self,
        constraints: Dict[str, List[Dict[str, Any]]],
    ) -> Optional[int]:
        """Extract area budget from constraints."""
        for constraint in constraints.get("hard", []):
            if constraint["name"] in ["area", "area_budget"]:
                return int(constraint["value"])
        return None
    
    def _extract_power_budget(
        self,
        constraints: Dict[str, List[Dict[str, Any]]],
    ) -> Optional[float]:
        """Extract power budget from constraints."""
        for constraint in constraints.get("hard", []):
            if constraint["name"] in ["power", "power_budget"]:
                return float(constraint["value"])
        return None
    
    def _estimate_area(self, architecture: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate area metrics.
        
        Args:
            architecture: Module hierarchy
        
        Returns:
            Area estimation dictionary
        """
        total_gates = 0
        total_registers = 0
        
        # Analyze modules
        hierarchy = architecture.get("hierarchy", {})
        modules = hierarchy.get("modules", [])
        
        for module in modules:
            module_type = module.get("type", "default")
            module_name = module.get("name", "")
            
            # Get complexity factors
            complexity = self._infer_module_complexity(module_name, module_type)
            
            total_gates += complexity["gates"]
            total_registers += complexity["ffs"]
            
            # Add memory if present
            params = module.get("parameters", {})
            if "FIFO_DEPTH" in params or "NUM_REGS" in params:
                depth = params.get("FIFO_DEPTH", params.get("NUM_REGS", 0))
                width = params.get("DATA_WIDTH", 32)
                memory_bits = depth * width
                total_registers += depth  # Approximation
        
        # Estimate combinational logic
        combinational_gates = total_gates - total_registers * self.tech_params["ff_area_ge"]
        
        return {
            "total_gates": total_gates,
            "breakdown": {
                "registers": total_registers,
                "combinational": max(0, combinational_gates),
                "memory_bits": 0,  # Would need deeper analysis
            },
            "unit": "gate_equivalents",
            "technology": self.technology,
            "utilization": {
                "estimated_area_mm2": total_gates * 0.00001,  # Rough estimate
                "fpga_luts": int(total_gates * 0.3),  # FPGA approximation
                "fpga_ffs": total_registers,
            }
        }
    
    def _estimate_timing(
        self,
        architecture: Dict[str, Any],
        area: Dict[str, Any],
        target_freq_mhz: float,
    ) -> Dict[str, Any]:
        """Estimate timing metrics.
        
        Args:
            architecture: Module hierarchy
            area: Area estimation
            target_freq_mhz: Target frequency
        
        Returns:
            Timing estimation dictionary
        """
        # Estimate critical path based on module types
        hierarchy = architecture.get("hierarchy", {})
        modules = hierarchy.get("modules", [])
        
        # Calculate logic depth
        logic_levels = 5  # Default assumption
        worst_freq_factor = 1.0
        
        for module in modules:
            module_name = module.get("name", "")
            complexity = self._infer_module_complexity(module_name, module.get("type", ""))
            worst_freq_factor = min(worst_freq_factor, complexity["freq_factor"])
        
        # Calculate max frequency
        gate_delay_ns = self.tech_params["gate_delay_ps"] / 1000
        critical_path_ns = logic_levels * gate_delay_ns / worst_freq_factor
        max_freq_mhz = 1000 / critical_path_ns
        
        # Calculate slack
        target_period_ns = 1000 / target_freq_mhz
        slack_ns = target_period_ns - critical_path_ns
        
        return {
            "max_freq_mhz": round(max_freq_mhz, 1),
            "min_period_ns": round(critical_path_ns, 2),
            "critical_path": {
                "delay_ns": round(critical_path_ns, 2),
                "slack_ns": round(slack_ns, 2),
                "startpoint": "estimated",
                "endpoint": "estimated",
                "logic_levels": logic_levels,
            },
            "clock_domains": [
                {
                    "name": "clk",
                    "frequency_mhz": target_freq_mhz,
                    "period_ns": target_period_ns,
                }
            ],
            "constraints": {
                "input_delay_ns": 1.0,
                "output_delay_ns": 1.5,
                "clock_uncertainty_ns": 0.3,
            }
        }
    
    def _estimate_power(
        self,
        area: Dict[str, Any],
        timing: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Estimate power consumption.
        
        Args:
            area: Area estimation
            timing: Timing estimation
        
        Returns:
            Power estimation dictionary
        """
        total_gates = area["total_gates"]
        registers = area["breakdown"]["registers"]
        freq_mhz = timing["clock_domains"][0]["frequency_mhz"]
        
        # Dynamic power (switching activity)
        activity_factor = 0.2  # Assume 20% average switching
        switches_per_sec = freq_mhz * 1e6 * registers * activity_factor
        dynamic_power_pj = switches_per_sec * self.tech_params["dynamic_power_pj_per_switch"]
        dynamic_mw = dynamic_power_pj / 1e9  # Convert to mW
        
        # Static power (leakage)
        static_mw = (total_gates * self.tech_params["leakage_power_nw_per_ge"]) / 1e6
        
        # Breakdown
        clock_tree_mw = dynamic_mw * 0.25  # 25% of dynamic
        logic_mw = dynamic_mw * 0.55
        io_mw = dynamic_mw * 0.20
        
        return {
            "dynamic_mw": round(dynamic_mw, 2),
            "static_mw": round(static_mw, 2),
            "total_mw": round(dynamic_mw + static_mw, 2),
            "voltage": self.tech_params["voltage"],
            "breakdown": {
                "clock_tree_mw": round(clock_tree_mw, 2),
                "logic_mw": round(logic_mw, 2),
                "io_mw": round(io_mw, 2),
                "leakage_mw": round(static_mw, 2),
            },
            "conditions": {
                "temperature_c": 25,
                "activity_factor": activity_factor,
            }
        }
    
    def _assess_feasibility(
        self,
        area: Dict[str, Any],
        timing: Dict[str, Any],
        power: Dict[str, Any],
        constraints: Dict[str, List[Dict[str, Any]]],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Assess design feasibility.
        
        Args:
            area, timing, power: Estimated metrics
            constraints: Design constraints
        
        Returns:
            Tuple of (feasibility_level, warnings_list)
        """
        warnings = []
        violation_count = 0
        
        # Check timing
        slack = timing["critical_path"]["slack_ns"]
        if slack < 0:
            warnings.append({
                "severity": "error",
                "category": "timing",
                "message": f"时序违规：裕量为 {slack:.2f} ns (负值)",
                "affected_modules": ["top"],
            })
            violation_count += 1
        elif slack < 0.5:
            warnings.append({
                "severity": "warning",
                "category": "timing",
                "message": f"时序裕量较小：{slack:.2f} ns，建议优化",
                "affected_modules": ["top"],
            })
        
        # Check area budget
        area_budget = self._extract_area_budget(constraints)
        if area_budget and area["total_gates"] > area_budget:
            warnings.append({
                "severity": "error",
                "category": "area",
                "message": f"面积超出预算：{area['total_gates']} > {area_budget} GE",
                "affected_modules": ["top"],
            })
            violation_count += 1
        
        # Check power budget
        power_budget = self._extract_power_budget(constraints)
        if power_budget and power["total_mw"] > power_budget:
            warnings.append({
                "severity": "warning",
                "category": "power",
                "message": f"功耗接近预算：{power['total_mw']} / {power_budget} mW",
                "affected_modules": ["top"],
            })
        
        # Determine feasibility
        if violation_count == 0:
            feasibility = "high"
        elif violation_count <= 2:
            feasibility = "medium"
        else:
            feasibility = "low"
        
        return feasibility, warnings
    
    def _infer_module_complexity(
        self,
        module_name: str,
        module_type: str,
    ) -> Dict[str, Any]:
        """Infer module complexity from name and type.
        
        Args:
            module_name: Module name
            module_type: Module type (leaf, mid, top)
        
        Returns:
            Complexity factors (gates, ffs, freq_factor)
        """
        # Check for keyword matches
        name_lower = module_name.lower()
        
        for key, complexity in self.MODULE_COMPLEXITY.items():
            if key in name_lower:
                return complexity
        
        # Default based on type
        if module_type == "leaf":
            return self.MODULE_COMPLEXITY["default"]
        elif module_type == "mid":
            return {"gates": 1000, "ffs": 128, "freq_factor": 0.95}
        else:
            return {"gates": 2000, "ffs": 256, "freq_factor": 0.9}


# LangGraph node function
def ppa_estimation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node function for PPA estimation.
    
    Args:
        state: Current workflow state (expects 'architecture' and 'constraints')
    
    Returns:
        Updated state with 'ppa' field
    """
    estimator = PPAEstimator()
    
    architecture = state.get("architecture", {})
    constraints = state.get("constraints", {"hard": [], "soft": []})
    
    ppa = estimator.estimate(architecture, constraints)
    
    # Update version history with PPA snapshot
    versions = state.get("versions", [])
    if versions:
        versions[-1]["ppa_snapshot"] = ppa
    
    return {
        "ppa": ppa,
        "versions": versions,
    }
