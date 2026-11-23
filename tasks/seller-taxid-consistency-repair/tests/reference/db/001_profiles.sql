CREATE OR ALTER PROCEDURE dbo.seller_profile_insert
 @seller_id varchar(48), @partner_id varchar(48), @person_type char(1)
AS
BEGIN
 SET NOCOUNT ON;
 INSERT dbo.seller_profile(seller_id,partner_id,person_type,created_at,modified_at)
 VALUES(@seller_id,@partner_id,@person_type,GETDATE(),GETDATE());
END;
GO
CREATE OR ALTER PROCEDURE dbo.seller_profile_update
 @seller_id varchar(48), @person_type char(1)=NULL,
 @account_tax_id varchar(32)=NULL, @contact_tax_id varchar(32)=NULL
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE dbo.seller_profile SET person_type=COALESCE(@person_type,person_type),
 account_tax_id=COALESCE(@account_tax_id,account_tax_id),
 contact_tax_id=COALESCE(@contact_tax_id,contact_tax_id),modified_at=GETDATE()
 WHERE seller_id=@seller_id;
END;
GO
