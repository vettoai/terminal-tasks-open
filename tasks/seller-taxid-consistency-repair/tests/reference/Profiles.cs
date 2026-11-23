using Microsoft.Data.SqlClient;
using System.Data;

namespace SellerRegistration;

public sealed class Integration
{
    public string Token { get; set; } = "";
    public string Kind { get; set; } = "";
    public string PartnerId { get; set; } = "";
}

public sealed class ProfileRequest
{
    public string? SellerId { get; set; }
    public string? PersonType { get; set; }
    public string? AccountTaxId { get; set; }
    public string? ContactTaxId { get; set; }
}

public sealed record Profile(string SellerId, string PartnerId, string PersonType,
    string? AccountTaxId, string? ContactTaxId, bool SecondContactRegistered, int Status);
public sealed record Reply(bool Success, string? Error = null);

public sealed class ProfileRepository(IConfiguration configuration)
{
    public SqlConnection Connection() => new(configuration.GetConnectionString("Sellers"));

    public async Task<bool> Healthy()
    {
        try { await using var connection = Connection(); await connection.OpenAsync(); return true; }
        catch (SqlException) { return false; }
    }

    public async Task<Profile?> Find(string id)
    {
        await using var connection = Connection();
        await connection.OpenAsync();
        await using var command = new SqlCommand("SELECT seller_id,partner_id,person_type,account_tax_id,contact_tax_id,second_contact_registered,status FROM dbo.seller_profile WHERE seller_id=@id", connection);
        command.Parameters.AddWithValue("@id", id);
        await using var reader = await command.ExecuteReaderAsync();
        if (!await reader.ReadAsync()) return null;
        return new(reader.GetString(0), reader.GetString(1), reader.GetString(2),
            reader.IsDBNull(3) ? null : reader.GetString(3), reader.IsDBNull(4) ? null : reader.GetString(4), reader.GetBoolean(5), reader.GetInt32(6));
    }

    public async Task<bool> AllowsSecondContact(Profile profile)
    {
        if (!profile.SecondContactRegistered) return false;
        await using var connection = Connection();
        await connection.OpenAsync();
        await using var command = new SqlCommand("SELECT COUNT(*) FROM dbo.partner_second_contact WHERE partner_id=@partner", connection);
        command.Parameters.AddWithValue("@partner", profile.PartnerId);
        return Convert.ToInt32(await command.ExecuteScalarAsync()) > 0;
    }

    public async Task LogPartnerUpdate(string id, ProfileRequest body, Integration caller)
    {
        await using var connection = Connection();
        await connection.OpenAsync();
        await using var command = new SqlCommand("INSERT dbo.partner_update_log(seller_id,requested_at,integration,body) VALUES(@id,GETDATE(),@integration,@body)", connection);
        command.Parameters.AddWithValue("@id", id);
        command.Parameters.AddWithValue("@integration", caller.Kind + ":" + caller.PartnerId);
        command.Parameters.AddWithValue("@body", System.Text.Json.JsonSerializer.Serialize(body, new System.Text.Json.JsonSerializerOptions(System.Text.Json.JsonSerializerDefaults.Web)));
        await command.ExecuteNonQueryAsync();
    }

    public async Task<bool> InUse(string id, string account)
    {
        await using var connection = Connection();
        await connection.OpenAsync();
        await using var command = new SqlCommand("SELECT COUNT(*) FROM dbo.seller_profile WHERE account_tax_id=@account AND seller_id<>@id AND status<>1", connection);
        command.Parameters.AddWithValue("@id", id);
        command.Parameters.AddWithValue("@account", account);
        return Convert.ToInt32(await command.ExecuteScalarAsync()) > 0;
    }

    public async Task Insert(string id, string partner, string person)
    {
        await using var connection = Connection();
        await connection.OpenAsync();
        await using var command = new SqlCommand("dbo.seller_profile_insert", connection) { CommandType = CommandType.StoredProcedure };
        command.Parameters.AddWithValue("@seller_id", id);
        command.Parameters.AddWithValue("@partner_id", partner);
        command.Parameters.AddWithValue("@person_type", person);
        await command.ExecuteNonQueryAsync();
    }

    public async Task Update(string id, string? person, string? account, string? contact)
    {
        await using var connection = Connection();
        await connection.OpenAsync();
        await using var command = new SqlCommand("dbo.seller_profile_update", connection) { CommandType = CommandType.StoredProcedure };
        command.Parameters.AddWithValue("@seller_id", id);
        command.Parameters.AddWithValue("@person_type", (object?)person ?? DBNull.Value);
        command.Parameters.AddWithValue("@account_tax_id", (object?)account ?? DBNull.Value);
        command.Parameters.AddWithValue("@contact_tax_id", (object?)contact ?? DBNull.Value);
        await command.ExecuteNonQueryAsync();
    }
}

public sealed class ProfileWriter(ProfileRepository repository)
{
    private static Reply? Validate(ProfileRequest body, Integration caller, string? account, string? contact)
    {
        if (body.PersonType == "F" && contact is not null && !TaxIds.Personal(contact)) return new(false, "Invalid contact document");
        if (body.PersonType is not null && body.PersonType != "F" && account is not null && !TaxIds.Company(account)) return new(false, "Invalid company document");
        if (caller.Kind == "external" && account is not null && !TaxIds.Personal(account) && !TaxIds.Company(account)) return new(false, "Invalid document");
        return null;
    }

    public async Task<Reply> Signup(ProfileRequest body, Integration caller)
    {
        if (string.IsNullOrWhiteSpace(body.SellerId)) return new(false, "Seller id required");
        var account = TaxIds.Normalize(body.AccountTaxId);
        var contact = TaxIds.Normalize(body.ContactTaxId);
        var error = Validate(body, caller, account, contact);
        if (error is not null) return error;
        if (await repository.Find(body.SellerId) is not null) return new(false, "Seller exists");
        if (account is not null && await repository.InUse(body.SellerId, account)) return new(false, "Document in use");
        await repository.Insert(body.SellerId, caller.PartnerId, body.PersonType == "F" ? "F" : "J");
        await repository.Update(body.SellerId, null, account, contact);
        return new(true);
    }

    public async Task<Reply> Save(string id, ProfileRequest body, Integration caller, bool partnerUpdate)
    {
        if (partnerUpdate) await repository.LogPartnerUpdate(id, body, caller);
        var stored = await repository.Find(id);
        if (stored is null) return new(false, "Seller not found");
        var account = TaxIds.Normalize(body.AccountTaxId);
        var contact = TaxIds.Normalize(body.ContactTaxId);
        var error = Validate(body, caller, account, contact);
        if (error is not null) return error;
        if (account is not null && await repository.InUse(id, account)) return new(false, "Document in use");
        await repository.Update(id, body.PersonType is null ? null : body.PersonType == "F" ? "F" : "J", account, contact);
        return new(true);
    }
}
