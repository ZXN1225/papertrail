"""Typed whitelist of business tools; no SQL, shell, or arbitrary URL access."""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from pydantic import Field, StrictInt, StrictStr

from app.agent.contracts import ToolCall, ToolObservation
from app.catalog.contracts import Category, Region
from app.common.contracts import Contract
from app.compatibility.contracts import CompatibilityRequest
from app.compatibility.service import CompatibilityService
from app.recommendation.contracts import LaptopRankRequest, PcSolveRequest
from app.recommendation.pc_solver import PcSolver
from app.recommendation.service import LaptopRanker


class SearchCatalogArgs(Contract):
    category: Category | None = None
    region: Region = "CN"
    query: Annotated[StrictStr, Field(max_length=120)] | None = None
    limit: Annotated[StrictInt, Field(ge=1, le=20)] = 20


class FactsArgs(Contract):
    sku_ids: Annotated[list[UUID], Field(min_length=1, max_length=10)]
    fields: list[Annotated[StrictStr, Field(min_length=1, max_length=80)]] | None = Field(
        default=None, max_length=40
    )


class OffersArgs(Contract):
    sku_id: UUID
    region: Region = "CN"


class CompatibilityArgs(CompatibilityRequest):
    pass


class ToolRegistry:
    """Maps model-visible names to validated domain-service calls only."""

    def __init__(self, catalog):
        self.catalog = catalog
        self.schemas = {
            "search_catalog": SearchCatalogArgs,
            "get_product_facts": FactsArgs,
            "get_offers": OffersArgs,
            "rank_laptops": None,
            "solve_pc_builds": None,
            "check_compatibility": CompatibilityArgs,
        }

    def schema_names(self):
        return sorted(self.schemas)

    @staticmethod
    def _evidence_ids(data):
        if not isinstance(data, dict):
            return []
        facts = data.get("facts", [])
        ids = []
        for fact in facts:
            if isinstance(fact, dict) and fact.get("id"):
                ids.append(fact["id"])
        return ids

    def execute(self, call: ToolCall, profile):
        if call.name not in self.schemas:
            raise ValueError("Tool is not allowed")
        if call.name == "search_catalog":
            args = SearchCatalogArgs.model_validate(call.arguments)
            data = self.catalog.list_products(
                args.category, args.region, args.query, None, args.limit
            )
        elif call.name == "get_product_facts":
            args = FactsArgs.model_validate(call.arguments)
            products = []
            for sku_id in args.sku_ids:
                product = self.catalog.product(sku_id)
                if args.fields is not None:
                    product = {
                        **product,
                        "facts": [fact for fact in product["facts"] if fact["key"] in args.fields],
                    }
                products.append(product)
            data = {"products": products, "data_version": products[0]["data_version"]}
        elif call.name == "get_offers":
            args = OffersArgs.model_validate(call.arguments)
            data = self.catalog.offers(args.sku_id, args.region)
        elif call.name == "rank_laptops":
            if call.arguments:
                raise ValueError("rank_laptops derives constraints from the saved profile")
            if profile.mode != "laptop":
                raise ValueError("Saved profile mode is not laptop")
            constraints = profile.laptop_constraints
            data = LaptopRanker(self.catalog).rank(
                LaptopRankRequest(
                    region=profile.market,
                    budget_minor=profile.budget_max_minor,
                    max_weight_g=constraints.max_weight_g if constraints else None,
                    excluded_brands=profile.excluded_brands,
                )
            )
        elif call.name == "solve_pc_builds":
            if call.arguments:
                raise ValueError("solve_pc_builds derives constraints from the saved profile")
            if profile.mode != "pc":
                raise ValueError("Saved profile mode is not pc")
            requirements = {}
            if profile.pc_constraints and profile.pc_constraints.wifi_required is not None:
                requirements["wifi"] = profile.pc_constraints.wifi_required
            data = PcSolver(self.catalog).solve(
                PcSolveRequest(
                    region=profile.market,
                    budget_minor=profile.budget_max_minor,
                    excluded_brands=profile.excluded_brands,
                    hard_requirements=requirements,
                )
            )
        else:
            args = CompatibilityArgs.model_validate(call.arguments)
            data = CompatibilityService(self.catalog).check(args)
        # Tool observations are JSON-only; providers never receive live service objects.
        data = json.loads(json.dumps(data, default=str))
        version = data.get("data_version") or data.get("candidate_pool_version")
        return ToolObservation(
            name=call.name,
            status="partial"
            if data.get("status") in {"no_candidates", "incomplete_search"}
            else "ok",
            data=data,
            evidence_ids=self._evidence_ids(data),
            missing_fields=data.get("missing_data", []),
            data_version=version,
        )
