# ERP Domain Model

## Product and inventory
Product -> Variant -> SKU -> InventoryItem -> StockLedger. Inventory is ledger-backed; adjustments are append-only business events. Available stock is derived from on-hand minus reservations.

## Procurement
Supplier -> RFQ -> PurchaseOrder -> GoodsReceipt -> SupplierInvoice -> Payment. Approval policy is configurable and audited.

## Manufacturing
BOM -> WorkOrder -> MaterialIssue -> ProductionReceipt -> QualityInspection. Lot/batch records preserve raw-material and finished-goods traceability.

## Sales and fulfillment
Customer -> SalesOrder -> Reservation -> Pick -> Pack -> Shipment -> Delivery -> Return/Refund.

## Accounting
Journal entries use balanced double-entry accounting. Operational events post through explicit posting rules; journal lines are immutable after posting and corrected through reversal/adjustment entries.

## Analytics
Core metrics include gross margin, inventory turnover, AOV, engagement rate, conversion rate, RPM, LTV and RFM. Recommendation/viral scores are configurable business heuristics with minimum-sample thresholds and must not be described as platform ranking algorithms.
