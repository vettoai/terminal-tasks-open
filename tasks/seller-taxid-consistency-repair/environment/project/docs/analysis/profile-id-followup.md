# Document follow-up — September 26

Otavio Reis, application-support engineer

Support's invoice complaints led me to compare the two document fields for individual sellers. I used:

```sql
SELECT COUNT(*) AS divergent,
 SUM(CASE WHEN modified_at > created_at THEN 1 ELSE 0 END) AS later_modified
FROM dbo.seller_profile
WHERE person_type='F'
  AND ISNULL(account_tax_id,'') <> ISNULL(contact_tax_id,'');
```

The result was 416 divergent profiles and 416 modified after creation. That points to updates after onboarding rather than bad registration data. The January 2022 registration change looks like the likely starting point; the old accounts probably acquired the mismatch when updated afterward.

S-1042 is a recent example: the dashboard has a CPF while the account has a CNPJ. The closed support cases say re-saving the profile resolved the invoice complaints. I have linked the ticket export under docs/support for the next support rotation.
