"""Durable background workers.

Workers perform transport and retry orchestration only. Financial state changes
remain exclusively inside ``ReconcilePaymentUseCase`` transactions.
"""
